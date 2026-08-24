"""Backend for the MiniMax H3 Timeline Director node.

The UI stores an edit decision list (EDL) in ``timeline_data``.  At queue time
this module resolves the current generation selection into the exact inputs of
ComfyUI's official ``MiniMaxH3ReferenceToVideo`` node:

* selected portions of timeline video clips become reference videos;
* their source soundtracks become index-paired reference-video audio;
* frames immediately outside the selection become boundary reference images;
* a gap between two clips uses the left clip's last and right clip's first frame;
* standalone image and audio assets are forwarded as references.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Iterable

import av
import numpy as np
import torch
from aiohttp import web
from PIL import Image, ImageOps

import folder_paths
import node_helpers
from comfy_api.latest import io
from comfy_extras import nodes_minimax_h3 as h3_nodes
from server import PromptServer


log = logging.getLogger("MiniMaxH3TimelineDirector")
FPS = 24.0
MAX_REF_IMAGES = 9
MAX_REF_VIDEOS = 3
MAX_REF_AUDIOS = 3
MAX_REF_VIDEO_SECONDS = 15.0
MIN_REF_VIDEO_SECONDS = 5.0 / FPS
UPLOAD_SUBDIR = "minimax_h3_timeline_director"
PREVIEW_SUBDIR = f"{UPLOAD_SUBDIR}/preview_proxies"
PREVIEW_MAX_WIDTH = 480
PREVIEW_MAX_HEIGHT = 270
PREVIEW_FPS = 12


def _upload_root() -> Path:
    root = Path(folder_paths.get_input_directory()).resolve() / UPLOAD_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(value: str) -> str:
    name = Path(str(value or "media")).name
    stem = re.sub(r"[^\w.()\-\u4e00-\u9fff]+", "_", name, flags=re.UNICODE)
    return (stem or "media")[:180]


def _safe_input_path(relative_name: str) -> Path:
    root = Path(folder_paths.get_input_directory()).resolve()
    candidate = (root / str(relative_name or "").replace("/", os.sep)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Media path is outside ComfyUI input directory") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"Reference media not found: {relative_name}")
    return candidate


def _relative_input(path: Path) -> str:
    root = Path(folder_paths.get_input_directory()).resolve()
    return path.resolve().relative_to(root).as_posix()


def _preview_root() -> Path:
    root = Path(folder_paths.get_input_directory()).resolve() / Path(PREVIEW_SUBDIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ensure_preview_proxy(source: Path) -> str:
    """Create a cached, silent low-resolution MP4 for timeline monitoring."""

    stat = source.stat()
    fingerprint = hashlib.sha1(
        f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|v1".encode("utf-8")
    ).hexdigest()[:16]
    destination = _preview_root() / f"{_safe_name(source.stem)[:80]}_{fingerprint}.mp4"
    if destination.is_file() and destination.stat().st_size > 1024:
        return _relative_input(destination)

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("ComfyUI environment does not provide ffmpeg for low-resolution preview") from exc

    temporary = destination.with_name(f".{destination.stem}_{uuid.uuid4().hex}.tmp.mp4")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-map", "0:v:0", "-an", "-vf",
        (
            f"fps={PREVIEW_FPS},scale={PREVIEW_MAX_WIDTH}:{PREVIEW_MAX_HEIGHT}:"
            "force_original_aspect_ratio=decrease:force_divisible_by=2"
        ),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
    ]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False,
            creationflags=creation_flags, timeout=600,
        )
        if completed.returncode != 0 or not temporary.is_file():
            detail = (completed.stderr or completed.stdout or "unknown ffmpeg error").strip()[-1200:]
            raise RuntimeError(f"Low-resolution preview creation failed: {detail}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return _relative_input(destination)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _media_info(path: Path, include_peaks: bool = True) -> dict[str, Any]:
    info: dict[str, Any] = {
        "filename": _relative_input(path),
        "name": path.name,
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "hasVideo": False,
        "hasAudio": False,
        "peaks": [],
    }
    with av.open(str(path)) as container:
        if container.duration is not None:
            info["duration"] = max(0.0, float(container.duration / av.time_base))
        if container.streams.video:
            stream = container.streams.video[0]
            info.update(
                hasVideo=True,
                width=int(stream.width or stream.codec_context.width or 0),
                height=int(stream.height or stream.codec_context.height or 0),
                fps=float(stream.average_rate or stream.guessed_rate or 0),
            )
            if not info["duration"] and stream.duration is not None and stream.time_base:
                info["duration"] = float(stream.duration * stream.time_base)
        if container.streams.audio:
            info["hasAudio"] = True
            stream = container.streams.audio[0]
            if not info["duration"] and stream.duration is not None and stream.time_base:
                info["duration"] = float(stream.duration * stream.time_base)
    if include_peaks and info["hasAudio"]:
        try:
            info["peaks"] = _audio_peaks(path)
        except Exception as exc:
            log.debug("Waveform extraction failed for %s: %s", path, exc)
    return info


def _decode_audio(path: Path, start: float = 0.0, duration: float | None = None) -> dict[str, Any] | None:
    """Decode an audio interval to ComfyUI AUDIO at 44.1 kHz.

    Seeking starts slightly early so compressed sources do not lose samples at
    a keyframe/packet boundary.  The decoded waveform is then sliced using the
    first decoded timestamp.
    """

    target_rate = 44100
    start = max(0.0, float(start))
    end = None if duration is None else start + max(0.0, float(duration))
    chunks: list[np.ndarray] = []
    first_time: float | None = None
    with av.open(str(path)) as container:
        if not container.streams.audio:
            return None
        stream = container.streams.audio[0]
        seek_to = max(0.0, start - 1.0)
        if seek_to > 0:
            container.seek(int(seek_to * av.time_base), backward=True)
        layout = "stereo" if getattr(stream.codec_context, "channels", 1) > 1 else "mono"
        resampler = av.AudioResampler(format="fltp", layout=layout, rate=target_rate)
        stop_after = None if end is None else end + 1.0
        for frame in container.decode(stream):
            frame_time = float(frame.time) if frame.time is not None else seek_to
            if first_time is None:
                first_time = frame_time
            if stop_after is not None and frame_time > stop_after:
                break
            converted = resampler.resample(frame)
            if not isinstance(converted, list):
                converted = [converted]
            for out in converted:
                arr = out.to_ndarray()
                if arr.ndim == 1:
                    arr = arr[None, :]
                chunks.append(arr.astype(np.float32, copy=False))
        flushed = resampler.resample(None)
        if not isinstance(flushed, list):
            flushed = [flushed] if flushed is not None else []
        for out in flushed:
            arr = out.to_ndarray()
            if arr.ndim == 1:
                arr = arr[None, :]
            chunks.append(arr.astype(np.float32, copy=False))
    if not chunks:
        return None
    waveform = np.concatenate(chunks, axis=1)
    decoded_start = max(0.0, first_time or 0.0)
    begin = max(0, int(round((start - decoded_start) * target_rate)))
    finish = waveform.shape[1] if end is None else min(
        waveform.shape[1], int(round((end - decoded_start) * target_rate))
    )
    if finish <= begin:
        return None
    tensor = torch.from_numpy(np.ascontiguousarray(waveform[:, begin:finish])).unsqueeze(0)
    return {"waveform": tensor, "sample_rate": target_rate}


def _empty_audio(sample_rate: int = 44100) -> dict[str, Any]:
    return {"waveform": torch.zeros((1, 1, 1), dtype=torch.float32), "sample_rate": sample_rate}


def _audio_channels(waveform: torch.Tensor, channels: int) -> torch.Tensor:
    """Normalize ComfyUI [B,C,T] audio to a common channel count."""

    waveform = waveform[:1].to(dtype=torch.float32, device="cpu")
    current = waveform.shape[1]
    if current == channels:
        return waveform
    if current == 1:
        return waveform.repeat(1, channels, 1)
    if channels == 1:
        return waveform.mean(dim=1, keepdim=True)
    if current > channels:
        return waveform[:, :channels]
    return torch.cat([waveform, waveform[:, -1:].repeat(1, channels - current, 1)], dim=1)


def _timeline_video_audio(timeline: dict[str, Any], sample_rate: int = 44100) -> dict[str, Any]:
    """Mix every edited video soundtrack at its timeline position, including gaps."""

    decoded: list[tuple[int, torch.Tensor]] = []
    channels = 1
    timeline_samples = 0
    clips = [c for c in timeline.get("videoClips", []) if isinstance(c, dict) and c.get("file")]
    for clip in sorted(clips, key=lambda item: _float(item.get("start"))):
        start = max(0.0, _float(clip.get("start")))
        duration = max(0.0, _float(clip.get("duration")))
        timeline_samples = max(timeline_samples, int(round((start + duration) * sample_rate)))
        if not clip.get("hasAudio", True) or duration <= 0:
            continue
        audio = _decode_audio(
            _safe_input_path(str(clip["file"])), max(0.0, _float(clip.get("trimStart"))), duration
        )
        if audio is None:
            continue
        waveform = audio["waveform"]
        channels = max(channels, int(waveform.shape[1]))
        decoded.append((int(round(start * sample_rate)), waveform))
    if not decoded:
        return {
            "waveform": torch.zeros((1, 1, max(1, timeline_samples)), dtype=torch.float32),
            "sample_rate": sample_rate,
        }
    mixed = torch.zeros((1, channels, max(1, timeline_samples)), dtype=torch.float32)
    for offset, waveform in decoded:
        normalized = _audio_channels(waveform, channels)
        available = max(0, mixed.shape[-1] - offset)
        count = min(available, normalized.shape[-1])
        if count:
            mixed[..., offset : offset + count] += normalized[..., :count]
    return {"waveform": mixed.clamp_(-1.0, 1.0), "sample_rate": sample_rate}


def _standalone_audio_track(timeline: dict[str, Any], sample_rate: int = 44100) -> dict[str, Any]:
    """Concatenate independent reference audios in their visible upload order."""

    waveforms: list[torch.Tensor] = []
    channels = 1
    for asset in timeline.get("audios", []):
        if not isinstance(asset, dict) or not asset.get("file"):
            continue
        duration = _float(asset.get("duration")) or None
        audio = _decode_audio(
            _safe_input_path(str(asset["file"])), max(0.0, _float(asset.get("trimStart"))), duration
        )
        if audio is None:
            continue
        waveform = audio["waveform"]
        channels = max(channels, int(waveform.shape[1]))
        waveforms.append(waveform)
    if not waveforms:
        return _empty_audio(sample_rate)
    merged = torch.cat([_audio_channels(waveform, channels) for waveform in waveforms], dim=-1)
    return {"waveform": merged, "sample_rate": sample_rate}


def _audio_peaks(path: Path, count: int = 180) -> list[float]:
    """Build a fixed-size waveform preview without retaining the full soundtrack."""

    preview_rate = 8000
    peaks = np.zeros(count, dtype=np.float32)
    with av.open(str(path)) as container:
        if not container.streams.audio:
            return []
        stream = container.streams.audio[0]
        duration = float(container.duration / av.time_base) if container.duration else 0.0
        if not duration and stream.duration is not None and stream.time_base:
            duration = float(stream.duration * stream.time_base)
        # Unknown-duration streams are rare for uploaded files.  Give them a
        # conservative ten-minute preview span while keeping memory constant.
        total_samples = max(count, int(math.ceil(max(duration, 600.0 if not duration else duration) * preview_rate)))
        bin_size = max(1, int(math.ceil(total_samples / count)))
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=preview_rate)
        position = 0

        def consume(array: np.ndarray) -> None:
            nonlocal position
            values = np.abs(array.reshape(-1).astype(np.float32, copy=False))
            offset = 0
            while offset < values.size:
                bucket = min(count - 1, position // bin_size)
                take = min(values.size - offset, bin_size - (position % bin_size))
                if take > 0:
                    peaks[bucket] = max(peaks[bucket], float(values[offset : offset + take].max(initial=0.0)))
                position += take
                offset += take

        for frame in container.decode(stream):
            converted = resampler.resample(frame)
            if not isinstance(converted, list):
                converted = [converted]
            for out in converted:
                consume(out.to_ndarray())
        flushed = resampler.resample(None)
        if not isinstance(flushed, list):
            flushed = [flushed] if flushed is not None else []
        for out in flushed:
            consume(out.to_ndarray())
    return [float(value) for value in np.clip(peaks, 0.0, 1.0)]


def _target_size(width: Any = None, height: Any = None) -> tuple[int, int] | None:
    """Validate a generation canvas size used to bound decoded reference media."""

    target_width, target_height = int(_float(width)), int(_float(height))
    if target_width < 1 or target_height < 1:
        return None
    return target_width, target_height


def _fit_image(image: Image.Image, size: tuple[int, int], *, video: bool = False) -> Image.Image:
    """Aspect-fill a reference into the generation canvas without distortion."""

    method = Image.Resampling.BILINEAR if video else Image.Resampling.LANCZOS
    return ImageOps.fit(image.convert("RGB"), size, method=method, centering=(0.5, 0.5))


def _decode_video(
    path: Path,
    start: float,
    duration: float,
    fps: float = FPS,
    target_width: Any = None,
    target_height: Any = None,
) -> torch.Tensor | None:
    start = max(0.0, float(start))
    duration = max(0.0, float(duration))
    if duration <= 0:
        return None
    target_count = max(1, int(round(duration * fps)))
    target_times = [start + i / fps for i in range(target_count)]
    decoded: list[tuple[float, np.ndarray]] = []
    target_size = _target_size(target_width, target_height)
    with av.open(str(path)) as container:
        if not container.streams.video:
            return None
        stream = container.streams.video[0]
        seek_to = max(0.0, start - 1.0)
        if stream.time_base:
            container.seek(int(seek_to / float(stream.time_base)), stream=stream, backward=True)
        else:
            container.seek(int(seek_to * av.time_base), backward=True)
        limit = start + duration + 1.0 / fps
        fallback_time = seek_to
        source_fps = float(stream.average_rate or stream.guessed_rate or fps)
        for index, frame in enumerate(container.decode(stream)):
            timestamp = float(frame.time) if frame.time is not None else fallback_time + index / source_fps
            if timestamp < start - 1.0 / fps:
                continue
            if timestamp > limit:
                break
            if target_size:
                # Resize each decoded frame immediately.  This is deliberately
                # done before frames are retained, so a 4K/8K source never
                # accumulates a full-resolution reference tensor in RAM/VRAM.
                array = np.asarray(_fit_image(frame.to_image(), target_size, video=True), dtype=np.uint8)
            else:
                array = frame.to_ndarray(format="rgb24")
            decoded.append((timestamp, np.ascontiguousarray(array)))
    if not decoded:
        return None
    frames: list[np.ndarray] = []
    cursor = 0
    for target in target_times:
        while cursor + 1 < len(decoded) and abs(decoded[cursor + 1][0] - target) <= abs(decoded[cursor][0] - target):
            cursor += 1
        frames.append(decoded[cursor][1])
    array = np.stack(frames).astype(np.float32) / 255.0
    return torch.from_numpy(array)


def _decode_frame(
    path: Path, second: float, target_width: Any = None, target_height: Any = None
) -> torch.Tensor | None:
    frames = _decode_video(
        path, max(0.0, second), 1.0 / FPS, FPS, target_width, target_height
    )
    return None if frames is None else frames[:1]


def _load_image(path: Path, target_width: Any = None, target_height: Any = None) -> torch.Tensor:
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        target_size = _target_size(target_width, target_height)
        if target_size:
            image = _fit_image(image, target_size)
        arr = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(np.ascontiguousarray(arr)).unsqueeze(0)


def _aligned_h3_length(seconds: float) -> int:
    """Return the nearest H3-valid 5 + 17*n frame count."""

    requested = max(5.0 / FPS, float(seconds)) * FPS
    n = max(0, round((requested - 5.0) / 17.0))
    return int(5 + 17 * n)


def _windows(start: float, duration: float, limit: float = MAX_REF_VIDEO_SECONDS) -> Iterable[tuple[float, float]]:
    remaining = max(0.0, duration)
    cursor = start
    while remaining >= MIN_REF_VIDEO_SECONDS:
        piece = min(limit, remaining)
        yield cursor, piece
        cursor += piece
        remaining -= piece


def _clip_end(clip: dict[str, Any]) -> float:
    return _float(clip.get("start")) + max(0.0, _float(clip.get("duration")))


def _source_time(clip: dict[str, Any], timeline_second: float) -> float:
    return max(0.0, _float(clip.get("trimStart")) + timeline_second - _float(clip.get("start")))


def _pick_boundaries(clips: list[dict[str, Any]], selection_start: float, selection_end: float) -> list[tuple[dict[str, Any], float, str]]:
    """Choose the visual context immediately outside both selection edges."""

    if not clips:
        return []
    epsilon = 1.0 / FPS
    tolerance = 0.5 / FPS
    ordered = sorted(clips, key=lambda clip: (_float(clip.get("start")), _clip_end(clip)))
    result: list[tuple[dict[str, Any], float, str]] = []

    containing_start = next((
        c for c in ordered
        if _float(c.get("start")) < selection_start - tolerance
        and selection_start < _clip_end(c) - tolerance
    ), None)
    if containing_start:
        result.append((containing_start, max(_float(containing_start.get("start")), selection_start - epsilon), "selection-in"))
    else:
        left = [c for c in ordered if _clip_end(c) <= selection_start + epsilon]
        if left:
            clip = max(left, key=_clip_end)
            result.append((clip, max(_float(clip.get("start")), _clip_end(clip) - epsilon), "left-gap"))

    containing_end = next((
        c for c in ordered
        if _float(c.get("start")) + tolerance < selection_end
        and selection_end < _clip_end(c) - tolerance
    ), None)
    if containing_end:
        result.append((containing_end, min(_clip_end(containing_end) - epsilon, selection_end + epsilon), "selection-out"))
    else:
        right = [c for c in ordered if _float(c.get("start")) >= selection_end - epsilon]
        if right:
            clip = min(right, key=lambda c: _float(c.get("start")))
            result.append((clip, _float(clip.get("start")), "right-gap"))
    return result


def _parse_timeline(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Timeline data is invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Timeline data must be a JSON object")
    return data


def _build_references(
    timeline: dict[str, Any], target_width: Any = None, target_height: Any = None
) -> tuple[dict[str, torch.Tensor], dict[str, torch.Tensor], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    clips = [c for c in timeline.get("videoClips", []) if isinstance(c, dict) and c.get("file")]
    selection = timeline.get("selection") or {}
    selection_start = max(0.0, _float(selection.get("start")))
    selection_duration = max(MIN_REF_VIDEO_SECONDS, _float(selection.get("duration"), 5.0))
    selection_end = selection_start + selection_duration

    ref_images: dict[str, torch.Tensor] = {}
    ref_videos: dict[str, torch.Tensor] = {}
    ref_video_audios: dict[str, dict[str, Any]] = {}
    ref_audios: dict[str, dict[str, Any]] = {}
    video_audio_enabled = timeline.get("videoAudioEnabled", True) is not False

    # User-uploaded bins own their visible ordinal space: independent images
    # always begin at <Picture 1>. Automatic boundary frames follow them.
    for asset in timeline.get("images", []):
        if len(ref_images) >= MAX_REF_IMAGES:
            break
        if not isinstance(asset, dict) or not asset.get("file"):
            continue
        ref_images[f"ref_image_{len(ref_images)}"] = _load_image(
            _safe_input_path(str(asset["file"])), target_width, target_height
        )

    for clip, timeline_second, _kind in _pick_boundaries(clips, selection_start, selection_end):
        if len(ref_images) >= MAX_REF_IMAGES:
            break
        path = _safe_input_path(str(clip["file"]))
        frame = _decode_frame(
            path, _source_time(clip, timeline_second), target_width, target_height
        )
        if frame is not None:
            ref_images[f"ref_image_{len(ref_images)}"] = frame

    # Each selected source interval is a reference video.  Longer intervals are
    # split into H3's 15-second reference window, up to the official limit of 3.
    for clip in sorted(clips, key=lambda c: _float(c.get("start"))):
        if len(ref_videos) >= MAX_REF_VIDEOS:
            break
        overlap_start = max(selection_start, _float(clip.get("start")))
        overlap_end = min(selection_end, _clip_end(clip))
        overlap_duration = overlap_end - overlap_start
        if overlap_duration < MIN_REF_VIDEO_SECONDS:
            continue
        path = _safe_input_path(str(clip["file"]))
        source_start = _source_time(clip, overlap_start)
        for piece_start, piece_duration in _windows(source_start, overlap_duration):
            if len(ref_videos) >= MAX_REF_VIDEOS:
                break
            frames = _decode_video(
                path, piece_start, piece_duration, FPS, target_width, target_height
            )
            if frames is None or frames.shape[0] < 5:
                continue
            index = len(ref_videos)
            ref_videos[f"ref_video_{index}"] = frames
            if video_audio_enabled and clip.get("hasAudio", True):
                audio = _decode_audio(path, piece_start, piece_duration)
                if audio is not None:
                    ref_video_audios[f"ref_video_audio_{index}"] = audio

    for asset in timeline.get("audios", []):
        if len(ref_audios) >= MAX_REF_AUDIOS:
            break
        if not isinstance(asset, dict) or not asset.get("file"):
            continue
        start = max(0.0, _float(asset.get("trimStart")))
        duration = _float(asset.get("duration")) or None
        audio = _decode_audio(_safe_input_path(str(asset["file"])), start, duration)
        if audio is not None:
            ref_audios[f"ref_audio_{len(ref_audios)}"] = audio

    return ref_images, ref_videos, ref_video_audios, ref_audios


def _execute_h3_independent_first(
    clip, vae, audio_vae, prompt: str, width: int, height: int, length: int,
    ref_image_size: str, ref_images: dict[str, torch.Tensor],
    ref_videos: dict[str, torch.Tensor], ref_video_audios: dict[str, dict[str, Any]],
    ref_audios: dict[str, dict[str, Any]],
) -> tuple[Any, Any]:
    """H3 Ref2VA with standalone Audio ordinals before paired video soundtracks.

    The official node presents video soundtracks before standalone audio.  The
    director intentionally presents independent audio first so the visible bin
    is stable as <Audio 1>, <Audio 2>, ... regardless of timeline video refs.
    """

    latent, frame_count = h3_nodes._empty_av_latent(width, height, length)
    ref_items: list[dict[str, Any]] = []
    ref_blocks: list[dict[str, Any]] = []

    for image in (ref_images or {}).values():
        if image is None:
            continue
        image_height, image_width = image.shape[1], image.shape[2]
        if ref_image_size == "match":
            scale = min(1.0, math.sqrt((width * height) / (image_width * image_height)))
        else:
            scale = min(1.0, h3_nodes.REF_IMAGE_SHORT_EDGE / min(image_width, image_height))
        target_width = max(
            h3_nodes.CANVAS_MULTIPLE,
            round(image_width * scale / h3_nodes.CANVAS_MULTIPLE) * h3_nodes.CANVAS_MULTIPLE,
        )
        target_height = max(
            h3_nodes.CANVAS_MULTIPLE,
            round(image_height * scale / h3_nodes.CANVAS_MULTIPLE) * h3_nodes.CANVAS_MULTIPLE,
        )
        resized = h3_nodes._resize(image[:1], target_width, target_height, "disabled")
        encoded = vae.encode(resized)
        ref_items.append({"type": "image", "data": resized})
        ref_blocks.append({
            "kind": "image", "latent_h": target_height // 16,
            "latent_w": target_width // 16, "latent": encoded,
        })

    # Standalone references own Audio 1..N.
    for audio in (ref_audios or {}).values():
        if audio is None:
            continue
        audio_latent, ref_audio_t = h3_nodes._encode_ref_audio(audio_vae, audio)
        ref_items.append({"type": "audio"})
        ref_blocks.append({"kind": "audio", "ref_audio_t": ref_audio_t, "audio_latent": audio_latent})

    ref_video_audios = ref_video_audios or {}
    for name, video_frames in (ref_videos or {}).items():
        if video_frames is None:
            continue
        soundtrack = ref_video_audios.get("ref_video_audio_" + name.rsplit("_", 1)[-1])
        video_height, video_width = video_frames.shape[1], video_frames.shape[2]
        canvas_width, canvas_height = h3_nodes.adapt_canvas(video_width, video_height)
        if video_width * video_height < canvas_width * canvas_height:
            canvas_width = max(
                h3_nodes.CANVAS_MULTIPLE,
                round(video_width / h3_nodes.CANVAS_MULTIPLE) * h3_nodes.CANVAS_MULTIPLE,
            )
            canvas_height = max(
                h3_nodes.CANVAS_MULTIPLE,
                round(video_height / h3_nodes.CANVAS_MULTIPLE) * h3_nodes.CANVAS_MULTIPLE,
            )
        frames = h3_nodes._resize(video_frames, canvas_width, canvas_height, "disabled")
        if frames.shape[0] > frame_count:
            frames = frames[:frame_count]
        frame_total = frames.shape[0]
        if frame_total < 5:
            raise ValueError("MiniMax H3 reference videos need at least 5 frames (~0.2s at 24 fps)")
        while frame_total % 17 != 5:
            frame_total -= 1
        frames = frames[:frame_total]
        video_latent = vae.encode(frames)
        audio_latent, ref_audio_t = (None, 0)
        if soundtrack is not None:
            audio_latent, ref_audio_t = h3_nodes._encode_ref_audio(audio_vae, soundtrack)
            ref_items.append({"type": "audio"})
        sample_indices = list(range(0, frames.shape[0], h3_nodes.FPS // 2))
        qwen_frames = frames[sample_indices]
        ref_items.append({
            "type": "video", "data": qwen_frames,
            "timestamps": [index / 2.0 for index in range(len(sample_indices))],
        })
        ref_blocks.append({
            "kind": "video_audio" if ref_audio_t else "video",
            "latent_t": video_latent.shape[2], "latent_h": canvas_height // 16,
            "latent_w": canvas_width // 16, "ref_audio_t": ref_audio_t,
            "latent": video_latent, "audio_latent": audio_latent,
        })

    tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
    conditioning = clip.encode_from_tokens_scheduled(tokens)
    if ref_blocks:
        conditioning = node_helpers.conditioning_set_values(
            conditioning, {"minimax_refs": ref_blocks}
        )
    return conditioning, latent


@PromptServer.instance.routes.post("/minimax_h3_timeline/upload_chunk")
async def upload_chunk(request: web.Request) -> web.Response:
    post = await request.post()
    upload = post.get("file")
    if upload is None:
        return web.json_response({"error": "Missing file"}, status=400)
    filename = _safe_name(str(post.get("filename") or getattr(upload, "filename", "media")))
    chunk_index = int(post.get("chunk_index", 0))
    total_chunks = max(1, int(post.get("total_chunks", 1)))
    destination = (_upload_root() / filename).resolve()
    try:
        destination.relative_to(_upload_root())
    except ValueError:
        return web.json_response({"error": "Invalid filename"}, status=400)

    content = upload.file.read()

    def write_chunk() -> None:
        with destination.open("wb" if chunk_index == 0 else "ab") as handle:
            handle.write(content)

    await asyncio.get_running_loop().run_in_executor(None, write_chunk)
    if chunk_index + 1 < total_chunks:
        return web.json_response({"ok": True, "chunk": chunk_index})
    try:
        info = await asyncio.get_running_loop().run_in_executor(None, _media_info, destination)
        return web.json_response({"ok": True, **info})
    except Exception as exc:
        destination.unlink(missing_ok=True)
        return web.json_response({"error": f"Cannot read uploaded media: {exc}"}, status=400)


@PromptServer.instance.routes.get("/minimax_h3_timeline/media_info")
async def media_info(request: web.Request) -> web.Response:
    try:
        path = _safe_input_path(request.query.get("filename", ""))
        info = await asyncio.get_running_loop().run_in_executor(None, _media_info, path)
        return web.json_response(info)
    except (ValueError, FileNotFoundError) as exc:
        return web.json_response({"error": str(exc)}, status=404)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)


@PromptServer.instance.routes.get("/minimax_h3_timeline/preview_proxy")
async def preview_proxy(request: web.Request) -> web.Response:
    """Return (and lazily create) the cached low-resolution monitoring proxy."""

    try:
        path = _safe_input_path(request.query.get("filename", ""))
        proxy = await asyncio.get_running_loop().run_in_executor(None, _ensure_preview_proxy, path)
        return web.json_response({
            "proxy": proxy,
            "width": PREVIEW_MAX_WIDTH,
            "height": PREVIEW_MAX_HEIGHT,
            "fps": PREVIEW_FPS,
        })
    except (ValueError, FileNotFoundError) as exc:
        return web.json_response({"error": str(exc)}, status=404)
    except Exception as exc:
        log.exception("Preview proxy failed")
        return web.json_response({"error": str(exc)}, status=400)


class MiniMaxH3TimelineDirector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3TimelineDirector",
            display_name="MiniMax H3 时间线导演台",
            description=(
                "在可编辑时间线中选择视频参考区域，自动组装参考视频、配套音频、"
                "边界首尾帧、独立图片与独立音频；独立素材从 1 编号，并输出合并音轨。"
            ),
            category="model/conditioning/minimax",
            inputs=[
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.String.Input("prompt", multiline=True, dynamic_prompts=True),
                io.Int.Input("width", default=1344, min=32, max=16384, step=32),
                io.Int.Input("height", default=768, min=32, max=16384, step=32),
                io.Float.Input(
                    "generation_seconds", default=5.0, min=0.21, max=150.0, step=0.1,
                    tooltip="要生成的时长，与时间线青色生成选区的长度双向同步。",
                ),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="match"),
                io.String.Input("timeline_data", default="", multiline=True),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(),
                io.Audio.Output(
                    display_name="视频原声合并",
                    tooltip="按时间轴位置混合所有视频片段的裁剪后原声，空隙保留静音。",
                ),
                io.Audio.Output(
                    display_name="独立音频合并",
                    tooltip="按素材箱顺序首尾拼接全部独立参考音频。",
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        clip,
        vae,
        audio_vae,
        prompt,
        width,
        height,
        generation_seconds,
        ref_image_size="match",
        timeline_data="",
    ) -> io.NodeOutput:
        timeline = _parse_timeline(timeline_data)
        target_width, target_height = int(width), int(height)
        ref_images, ref_videos, ref_video_audios, ref_audios = _build_references(
            timeline, target_width, target_height
        )
        if not (ref_images or ref_videos or ref_audios):
            raise ValueError(
                "导演台没有可用参考：请上传图片/音频，或让生成选择区覆盖视频片段/位于两段视频之间。"
            )
        length = _aligned_h3_length(_float(generation_seconds, 5.0))
        video_audio_output = _timeline_video_audio(timeline)
        standalone_audio_output = _standalone_audio_track(timeline)
        log.info(
            "Building H3 refs at %dx%d: %d images, %d videos, %d paired audios, %d standalone audios; %d output frames",
            target_width, target_height, len(ref_images), len(ref_videos),
            len(ref_video_audios), len(ref_audios), length,
        )
        conditioning, latent = _execute_h3_independent_first(
            clip, vae, audio_vae, prompt, target_width, target_height, length,
            ref_image_size, ref_images, ref_videos, ref_video_audios, ref_audios,
        )
        return io.NodeOutput(
            conditioning, latent, video_audio_output, standalone_audio_output
        )
