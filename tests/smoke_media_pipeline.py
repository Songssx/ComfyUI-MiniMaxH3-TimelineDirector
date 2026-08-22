"""Standalone smoke test for the director media pipeline.

Run with ComfyUI's Python from the ComfyUI directory:

    python tests/smoke_media_pipeline.py VIDEO IMAGE AUDIO
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import torch
from aiohttp import web
from server import PromptServer


def load_plugin(plugin_dir: Path):
    # ComfyUI creates PromptServer.instance in main.py.  A standalone media test
    # does not start the HTTP server, so provide only the route decorator surface.
    if not hasattr(PromptServer, "instance"):
        PromptServer.instance = types.SimpleNamespace(routes=web.RouteTableDef())
    package_name = "minimax_h3_timeline_director_smoke"
    spec = importlib.util.spec_from_file_location(
        package_name,
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.minimax_h3_timeline_director"]


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: smoke_media_pipeline.py VIDEO IMAGE AUDIO")
    plugin_dir = Path(__file__).resolve().parents[1]
    backend = load_plugin(plugin_dir)
    video, image, audio = sys.argv[1:]
    timeline = {
        "selection": {"start": 2.0, "duration": 5.0},
        "videoClips": [{
            "file": video,
            "start": 0.0,
            "duration": 10.0,
            "trimStart": 0.0,
            "sourceDuration": 10.0,
            "hasAudio": True,
        }],
        "images": [{"file": image}],
        "audios": [{"file": audio, "trimStart": 0.0, "duration": 3.0}],
    }
    # Reference media must be bounded to the node generation canvas before it
    # reaches the official H3 VAE path (protects against 4K/8K uploads).
    target_width, target_height = 320, 192
    images, videos, paired_audio, standalone_audio = backend._build_references(
        timeline, target_width, target_height
    )
    assert len(images) == 3, f"expected 2 boundary frames + 1 image, got {len(images)}"
    expected_picture_1 = backend._load_image(
        backend._safe_input_path(image), target_width, target_height
    )
    assert torch.allclose(images["ref_image_0"], expected_picture_1), "independent image must be Picture 1"
    assert len(videos) == 1 and videos["ref_video_0"].shape[0] == 120
    assert videos["ref_video_0"].shape == (120, target_height, target_width, 3)
    assert all(image.shape == (1, target_height, target_width, 3) for image in images.values())
    assert len(paired_audio) == 1
    assert paired_audio["ref_video_audio_0"]["waveform"].shape[-1] >= 4 * 44100
    assert len(standalone_audio) == 1
    assert standalone_audio["ref_audio_0"]["waveform"].shape[-1] == 3 * 44100
    assert backend._aligned_h3_length(5.0) == 124
    assert backend._aligned_h3_length(10.0) == 243
    video_track = backend._timeline_video_audio(timeline)
    independent_track = backend._standalone_audio_track(timeline)
    assert video_track["waveform"].shape[-1] == 10 * 44100
    assert independent_track["waveform"].shape[-1] == 3 * 44100
    two_audio_timeline = {"audios": [timeline["audios"][0], timeline["audios"][0]]}
    assert backend._standalone_audio_track(two_audio_timeline)["waveform"].shape[-1] == 6 * 44100

    # A five-second empty gap between two clips must produce only the two
    # bridge frames: last frame of the left clip + first frame of the right.
    gap_timeline = {
        "selection": {"start": 2.0, "duration": 5.0},
        "videoClips": [
            {"file": video, "start": 0.0, "duration": 2.0, "trimStart": 0.0, "hasAudio": True},
            {"file": video, "start": 7.0, "duration": 3.0, "trimStart": 7.0, "hasAudio": True},
        ],
        "images": [],
        "audios": [],
    }
    gap_images, gap_videos, gap_paired_audio, gap_audio = backend._build_references(
        gap_timeline, target_width, target_height
    )
    assert len(gap_images) == 2
    assert not gap_videos and not gap_paired_audio and not gap_audio
    gap_video_track = backend._timeline_video_audio(gap_timeline)
    assert gap_video_track["waveform"].shape[-1] == 10 * 44100
    assert torch.count_nonzero(gap_video_track["waveform"][..., 2 * 44100 : 7 * 44100]) == 0
    proxy = backend._ensure_preview_proxy(backend._safe_input_path(video))
    proxy_info = backend._media_info(backend._safe_input_path(proxy), include_peaks=False)
    assert proxy_info["hasVideo"] and not proxy_info["hasAudio"]
    assert proxy_info["width"] <= 480 and proxy_info["height"] <= 270
    assert 10 <= proxy_info["fps"] <= 13
    print(json.dumps({
        "images": [list(t.shape) for t in images.values()],
        "videos": [list(t.shape) for t in videos.values()],
        "paired_audio": [list(a["waveform"].shape) for a in paired_audio.values()],
        "standalone_audio": [list(a["waveform"].shape) for a in standalone_audio.values()],
        "length_5s": backend._aligned_h3_length(5.0),
        "length_10s": backend._aligned_h3_length(10.0),
        "gap_bridge_images": len(gap_images),
        "reference_canvas": [target_width, target_height],
        "audio_outputs": {
            "video_timeline_samples": video_track["waveform"].shape[-1],
            "standalone_samples": independent_track["waveform"].shape[-1],
            "two_standalone_samples": 6 * 44100,
            "gap_timeline_samples": gap_video_track["waveform"].shape[-1],
        },
        "preview_proxy": {
            "file": proxy,
            "width": proxy_info["width"],
            "height": proxy_info["height"],
            "fps": proxy_info["fps"],
            "has_audio": proxy_info["hasAudio"],
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
