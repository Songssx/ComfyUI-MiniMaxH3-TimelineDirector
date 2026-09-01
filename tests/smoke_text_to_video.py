"""Regression test for a material-free MiniMax H3 text-to-video plan.

Run with ComfyUI's Python from the plugin directory:

    python tests/smoke_text_to_video.py
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
    if not hasattr(PromptServer, "instance"):
        PromptServer.instance = types.SimpleNamespace(routes=web.RouteTableDef())
    package_name = "minimax_h3_text_to_video_smoke"
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


class FakeClip:
    def __init__(self):
        self.ref_items = None
        self.prompt = None

    def tokenize(self, prompt, minimax_ref_items):
        self.prompt = prompt
        self.ref_items = minimax_ref_items
        return {"tokens": prompt}

    @staticmethod
    def encode_from_tokens_scheduled(tokens):
        return [[torch.zeros((1, 1, 1)), {"tokens": tokens}]]


def main() -> None:
    plugin_dir = Path(__file__).resolve().parents[1]
    backend = load_plugin(plugin_dir)
    empty_latent = {"samples": torch.zeros((1, 8, 4, 4, 4))}
    backend.h3_nodes = types.SimpleNamespace(
        _empty_av_latent=lambda width, height, length: (empty_latent, length)
    )

    timeline = {
        "selection": {"start": 0.0, "duration": 5.0},
        "videoClips": [],
        "images": [],
        "audios": [],
    }
    plan = backend._create_timeline_plan(json.dumps(timeline), 640, 384, 5.0)
    clip = FakeClip()
    conditioning, latent, video_audio, standalone_audio = backend._encode_timeline_plan(
        plan, clip, vae=None, audio_vae=None,
        prompt="A paper boat crosses a quiet moonlit lake.", ref_image_size="match",
    )

    assert clip.ref_items == [], "pure T2V must not invent reference items"
    assert clip.prompt == "A paper boat crosses a quiet moonlit lake."
    assert conditioning[0][1]["tokens"]["tokens"] == clip.prompt
    assert latent is empty_latent
    assert "minimax_refs" not in conditioning[0][1]
    assert video_audio["waveform"].shape == (1, 1, 1)
    assert standalone_audio["waveform"].shape == (1, 1, 1)
    print("MiniMax H3 material-free text-to-video smoke test passed")


if __name__ == "__main__":
    main()
