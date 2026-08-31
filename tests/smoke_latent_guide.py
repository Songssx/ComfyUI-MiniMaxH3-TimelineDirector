"""Fast unit smoke test for the experimental direct-latent guide nodes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import torch
import types
from aiohttp import web
from comfy.nested_tensor import NestedTensor
from server import PromptServer


def _load_module(plugin_dir: Path):
    if not hasattr(PromptServer, "instance"):
        PromptServer.instance = types.SimpleNamespace(routes=web.RouteTableDef())
    package_name = "minimax_h3_latent_guide_smoke"
    spec = importlib.util.spec_from_file_location(
        package_name,
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.experimental_latent_guide"]


def _latent(video_tokens: int, marker: float = 0.0):
    video = torch.arange(video_tokens, dtype=torch.float32).reshape(1, 1, video_tokens, 1, 1)
    video = video.expand(1, 24, video_tokens, 4, 6).clone() + marker
    audio = torch.zeros((1, 32, 2, 200), dtype=torch.float32)
    return {"samples": NestedTensor((video, audio))}, video


def main():
    plugin_dir = Path(__file__).resolve().parents[1]
    experiment = _load_module(plugin_dir)
    experiment.MiniMaxH3AddLatentGuide.define_schema()
    experiment.MiniMaxH3VisualDifferenceMetrics.define_schema()

    # 124 source frames = 37 H3 video tokens; 22 guide frames = 7 tokens.
    source, source_video = _latent(37, marker=100.0)
    target, _ = _latent(37)
    positive = [[torch.zeros((1, 1, 1)), {}]]
    output = experiment.MiniMaxH3AddLatentGuide.execute(
        positive, target, source, guide_frames=24, frame_idx=0
    )
    conditioned, report = output[0], output[1]
    keyframes = conditioned[0][1]["minimax_keyframes"]
    assert len(keyframes) == 1
    keyframe = keyframes[0]
    assert keyframe["resolved_frame_index"] == 0
    assert keyframe["latent"].shape == (1, 24, 7, 4, 6)
    assert torch.equal(keyframe["latent"], source_video[:, :, -7:])
    assert "实际 22 帧 / 7 token" in report

    ref = torch.zeros((2, 8, 8, 3), dtype=torch.float32)
    cmp = torch.full_like(ref, 0.1)
    metrics = experiment.MiniMaxH3VisualDifferenceMetrics.execute(ref, cmp, 4.0)
    assert "MAE=0.100000" in metrics[0]
    assert torch.allclose(metrics[1], torch.full_like(ref, 0.4))
    print("latent guide smoke test: PASS")


if __name__ == "__main__":
    main()
