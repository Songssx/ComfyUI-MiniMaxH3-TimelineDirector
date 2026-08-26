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
    images, videos, paired_audio, standalone_audio, guides = backend._build_references(
        timeline, target_width, target_height, backend._aligned_h3_length(5.0)
    )
    assert len(images) == 1, f"native guides must not consume Picture ordinals, got {len(images)}"
    expected_picture_1 = backend._load_image(
        backend._safe_input_path(image), target_width, target_height
    )
    assert torch.allclose(images["ref_image_0"], expected_picture_1), "independent image must be Picture 1"
    assert len(videos) == 2, "the source context before and after the fixed overlap must be Video refs"
    assert videos["ref_video_0"].shape == (48, target_height, target_width, 3)
    assert videos["ref_video_1"].shape == (72, target_height, target_width, 3)
    assert all(image.shape == (1, target_height, target_width, 3) for image in images.values())
    assert len(paired_audio) == 2
    assert guides[0]["frame_idx"] == 0
    assert sum(g["image"].shape[0] for g in guides) == 120
    assert guides[-1]["frame_idx"] + guides[-1]["image"].shape[0] == 120
    assert all(g["audio"] is not None for g in guides)
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

    # Disabling video soundtrack references must keep the reference video and
    # independent audio, while omitting only ref_video_audio_N.
    muted_reference_timeline = json.loads(json.dumps(timeline))
    muted_reference_timeline["videoAudioEnabled"] = False
    muted_images, muted_videos, muted_paired_audio, muted_standalone_audio, muted_guides = backend._build_references(
        muted_reference_timeline, target_width, target_height
    )
    assert muted_images and muted_videos and muted_standalone_audio
    assert not muted_paired_audio
    assert muted_guides and all(g["audio"] is None for g in muted_guides)
    assert backend._timeline_video_audio(muted_reference_timeline)["waveform"].shape[-1] == 10 * 44100

    assert backend._valid_guide_frame_count(24) == 22
    assert backend._valid_guide_frame_count(4) == 1
    assert backend._guide_frame_slices(24) == [(0, 22), (22, 1), (23, 1)]
    boundary_clip = {"start": 0.0, "duration": 2.56, "trimStart": 1.65}
    assert backend._pick_gap_guides([boundary_clip], 0.0, 8.0) == []

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
    gap_images, gap_videos, gap_paired_audio, gap_audio, gap_guides = backend._build_references(
        gap_timeline, target_width, target_height
    )
    assert not gap_images
    assert not gap_videos and not gap_paired_audio and not gap_audio
    assert len(gap_guides) == 2
    assert [guide["frame_idx"] for guide in gap_guides] == [0, backend._aligned_h3_length(5.0) - 1]
    assert all(guide["image"].shape == (1, target_height, target_width, 3) for guide in gap_guides)

    # User acceptance mappings: a one-second edge overlap becomes a legal
    # 22-frame native guide; outside source context remains a Video reference.
    left_overlap = {
        "selection": {"start": 4.0, "duration": 9.0},
        "videoClips": [{"id": "left", "file": video, "start": 0.0, "duration": 5.0, "trimStart": 0.0, "hasAudio": True}],
        "images": [], "audios": [],
    }
    left_length = backend._aligned_h3_length(9.0)
    _, left_refs, _, _, left_guides = backend._build_references(
        left_overlap, target_width, target_height, left_length
    )
    assert len(left_refs) == 1 and left_guides[0]["frame_idx"] == 0
    assert sum(g["image"].shape[0] for g in left_guides) == 24

    both_edges = {
        "selection": {"start": 4.0, "duration": 9.0},
        "videoClips": [
            {"id": "left", "file": video, "start": 0.0, "duration": 5.0, "trimStart": 0.0, "hasAudio": True},
            {"id": "right", "file": video, "start": 12.0, "duration": 3.0, "trimStart": 0.0, "hasAudio": True},
        ], "images": [], "audios": [],
    }
    both_length = backend._aligned_h3_length(9.0)
    _, both_refs, _, _, both_guides = backend._build_references(
        both_edges, target_width, target_height, both_length
    )
    assert len(both_refs) == 2 and sum(g["image"].shape[0] for g in both_guides) == 48
    assert both_guides[0]["frame_idx"] == 0
    assert both_guides[-1]["frame_idx"] + both_guides[-1]["image"].shape[0] == both_length

    pure_gap = {
        "selection": {"start": 5.01, "duration": 2.96},
        "videoClips": [
            {"id": "left", "file": video, "start": 0.0, "duration": 5.01, "trimStart": 0.0, "hasAudio": True},
            {"id": "right", "file": video, "start": 7.97, "duration": 2.0, "trimStart": 0.0, "hasAudio": True},
        ], "images": [], "audios": [],
    }
    pure_gap_length = backend._aligned_h3_length(2.96)
    _, pure_gap_refs, _, _, pure_gap_guides = backend._build_references(
        pure_gap, target_width, target_height, pure_gap_length
    )
    assert not pure_gap_refs and len(pure_gap_guides) == 2
    assert [g["frame_idx"] for g in pure_gap_guides] == [0, pure_gap_length - 1]

    # Exercise the actual updated ComfyUI MiniMaxH3AddGuide implementation,
    # not merely the director's interval planner.
    class FakeVideoVAE:
        @staticmethod
        def encode(frames):
            return torch.zeros((1, 24, 1, max(1, frames.shape[1] // 16), max(1, frames.shape[2] // 16)))

    native_latent, _ = backend.h3_nodes._empty_av_latent(target_width, target_height, pure_gap_length)
    native_positive = [[torch.zeros((1, 1, 1)), {}]]
    applied = backend._apply_h3_guides(
        native_positive, native_latent, FakeVideoVAE(), None, pure_gap_guides
    )
    native_keyframes = applied[0][1]["minimax_keyframes"]
    assert [item["resolved_frame_index"] for item in native_keyframes] == [0, pure_gap_length - 1]

    # Per-clip edit mode must remove hard guides so identity/style replacement
    # can act on the complete source video. Boundary mode keeps only two stills.
    editable_timeline = {
        "selection": {"start": 0.0, "duration": 5.0},
        "videoClips": [{
            "id": "editable", "file": video, "start": 0.0, "duration": 5.0,
            "trimStart": 0.0, "hasAudio": True, "referenceMode": "edit",
        }], "images": [], "audios": [],
    }
    edit_images, edit_videos, edit_audio, _, edit_guides = backend._build_references(
        editable_timeline, target_width, target_height, backend._aligned_h3_length(5.0)
    )
    assert not edit_images and len(edit_videos) == 1 and len(edit_audio) == 1
    assert not edit_guides, "editable reference mode must not hard-lock the original person"

    boundary_timeline = json.loads(json.dumps(editable_timeline))
    boundary_timeline["videoClips"][0]["referenceMode"] = "boundary"
    _, boundary_videos, boundary_audio, _, boundary_guides = backend._build_references(
        boundary_timeline, target_width, target_height, backend._aligned_h3_length(5.0)
    )
    assert len(boundary_videos) == 1 and len(boundary_audio) == 1
    assert len(boundary_guides) == 2
    assert [guide["frame_idx"] for guide in boundary_guides] == [0, backend._aligned_h3_length(5.0) - 1]
    assert all(guide["audio"] is None and guide["image"].shape[0] == 1 for guide in boundary_guides)
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
        "native_guides": [{"frames": int(g["image"].shape[0]), "frame_idx": g["frame_idx"]} for g in guides],
        "gap_guides": len(gap_guides),
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
