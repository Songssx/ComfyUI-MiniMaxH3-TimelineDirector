"""Fast smoke tests for the MiniMax H3 generic-loop helper nodes."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import torch
from aiohttp import web
from comfy.nested_tensor import NestedTensor
from comfy.sampler_helpers import prepare_mask
from server import PromptServer


def _load_package(plugin_dir: Path):
    if not hasattr(PromptServer, "instance"):
        PromptServer.instance = types.SimpleNamespace(routes=web.RouteTableDef())
    package_name = "minimax_h3_loop_smoke"
    spec = importlib.util.spec_from_file_location(
        package_name,
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.minimax_h3_loop"]


def _latent(video_tokens: int, audio_tokens: int, marker: float = 0.0):
    video = torch.arange(video_tokens, dtype=torch.float32).reshape(1, 1, video_tokens, 1, 1)
    video = video.expand(1, 24, video_tokens, 4, 6).clone() + marker
    audio = torch.arange(audio_tokens, dtype=torch.float32).reshape(1, 1, 1, audio_tokens)
    audio = audio.expand(1, 32, 2, audio_tokens).clone() + marker
    return {"samples": NestedTensor((video, audio))}, video, audio


def main():
    plugin_dir = Path(__file__).resolve().parents[1]
    loop = _load_package(plugin_dir)
    loop.MiniMaxH3LoopPromptSelector.define_schema()
    loop.MiniMaxH3LoopLatentGuide.define_schema()
    loop.MiniMaxH3LoopSegmentFinalize.define_schema()

    source, source_video, source_audio = _latent(37, 207, marker=1000.0)
    target, _, _ = _latent(37, 207)
    positive = [[torch.zeros((1, 1, 1)), {}]]

    first = loop.MiniMaxH3LoopLatentGuide.execute(
        positive, target, True, 0, 24, True, None
    )
    assert first[0] is positive
    assert "minimax_keyframes" not in first[0][0][1]
    assert first[2] == 22
    assert "noise_mask" not in first[1]

    second = loop.MiniMaxH3LoopLatentGuide.execute(
        positive, target, False, 1, 24, True, source
    )
    keyframe = second[0][0][1]["minimax_keyframes"][0]
    assert keyframe["resolved_frame_index"] == 0
    assert keyframe["latent"].shape == (1, 24, 7, 4, 6)
    assert torch.equal(keyframe["latent"], source_video[:, :, -7:])
    assert keyframe["audio_latent"].shape == (1, 32, 2, 37)
    assert torch.equal(keyframe["audio_latent"], source_audio[..., -37:])
    masked_video, masked_audio = second[1]["samples"].unbind()
    video_mask, audio_mask = second[1]["noise_mask"].unbind()
    assert torch.equal(masked_video[:, :, :7], source_video[:, :, -7:])
    assert torch.equal(masked_audio[..., :37], source_audio[..., -37:])
    assert video_mask.shape == (1, 1, 37, 1, 1)
    assert audio_mask.shape == (1, 1, 1, 207)
    assert torch.allclose(video_mask[0, 0, :7, 0, 0], torch.linspace(0, 1, 7))
    assert torch.all(video_mask[:, :, 7:] == 1)
    assert torch.allclose(audio_mask[0, 0, 0, :37], torch.linspace(0, 1, 37))
    assert torch.all(audio_mask[..., 37:] == 1)
    assert "线性过渡" in second[3]
    assert prepare_mask(video_mask, masked_video.shape, "cpu").shape == masked_video.shape
    assert prepare_mask(audio_mask, masked_audio.shape, "cpu").shape == masked_audio.shape

    # The ramp length follows the aligned overlap dynamically: 41 -> 39 frames
    # -> 12 H3 video tokens. Disabling audio continuation leaves it fully noisy.
    target_no_audio, _, target_audio_no_guide = _latent(37, 207)
    dynamic = loop.MiniMaxH3LoopLatentGuide.execute(
        positive, target_no_audio, False, 2, 41, False, source
    )
    dynamic_video_mask, dynamic_audio_mask = dynamic[1]["noise_mask"].unbind()
    _, dynamic_audio = dynamic[1]["samples"].unbind()
    assert dynamic[2] == 39
    assert torch.allclose(
        dynamic_video_mask[0, 0, :12, 0, 0], torch.linspace(0, 1, 12)
    )
    assert torch.all(dynamic_video_mask[:, :, 12:] == 1)
    assert torch.all(dynamic_audio_mask == 1)
    assert torch.equal(dynamic_audio, target_audio_no_guide)

    images = torch.arange(124 * 2 * 3 * 3, dtype=torch.float32).reshape(124, 2, 3, 3)
    waveform = torch.arange(2 * 48000, dtype=torch.float32).reshape(1, 2, 48000)
    audio = {"waveform": waveform, "sample_rate": 48000}
    finalized_first = loop.MiniMaxH3LoopSegmentFinalize.execute(
        source, images, 0, 24, audio
    )
    assert finalized_first[0] is source
    assert finalized_first[1].shape[0] == 124
    assert finalized_first[2]["waveform"].shape[-1] == 48000

    finalized_second = loop.MiniMaxH3LoopSegmentFinalize.execute(
        source, images, 1, 24, audio
    )
    assert finalized_second[0] is source
    assert torch.equal(finalized_second[1], images[22:])
    assert torch.equal(finalized_second[2]["waveform"], waveform[..., 44000:])
    assert finalized_second[3] == 102

    prompt_1 = "integrated_multimodal_description:\n[Shot 1] First action.\noverall_soundscape:\nRoom.\nnon_diegetic_music:\nNone."
    prompt_2 = "integrated_multimodal_description:\n[Shot 1] Second action.\noverall_soundscape:\nRoom.\nnon_diegetic_music:\nNone."
    prompts = json.dumps([prompt_1, prompt_2])
    selected_first = loop.MiniMaxH3LoopPromptSelector.execute(0, prompts, 24, True)
    assert selected_first[0] == prompt_1
    assert "fixed latent continuation" not in selected_first[0]
    selected_second = loop.MiniMaxH3LoopPromptSelector.execute(1, prompts, 24, True)
    assert selected_second[1] == 2
    assert "fixed latent continuation" in selected_second[0]
    selected_repeated = loop.MiniMaxH3LoopPromptSelector.execute(5, prompts, 24, True)
    assert selected_repeated[1] == 2
    assert "重复最后一段" in selected_repeated[2]
    print("generic loop helper smoke test: PASS")


if __name__ == "__main__":
    main()
