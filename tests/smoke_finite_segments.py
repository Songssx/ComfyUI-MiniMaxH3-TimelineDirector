"""Structure smoke test for pure finite planning plus finite sampling."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import torch
from aiohttp import web
from server import PromptServer


def _load_package(plugin_dir: Path):
    if not hasattr(PromptServer, "instance"):
        PromptServer.instance = types.SimpleNamespace(routes=web.RouteTableDef())
    package_name = "minimax_h3_finite_smoke"
    spec = importlib.util.spec_from_file_location(
        package_name, plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.minimax_h3_finite_segments"]


def _plan():
    return {
        "type": "MINIMAX_H3_TIMELINE_PLAN", "version": 1,
        "width": 640, "height": 352, "generation_seconds": 8.0, "length": 192,
        "prompt_index": None, "segment_count": 3,
        "timeline": {
            "selection": {"start": 0.0, "duration": 8.0}, "clips": [],
            "images": [{"id": "p1", "file": "one.png"}, {"id": "p2", "file": "two.png"}],
            "audios": [{"id": "a1", "file": "one.wav"}, {"id": "a2", "file": "two.wav"}],
            "segmentConfig": {
                "count": 3,
                "segments": [
                    {"images": ["p1", "p2"], "audios": ["a1"]},
                    {"images": ["p2"], "audios": ["a2"]},
                    {"images": ["p1"], "audios": []},
                ],
            },
        },
    }


def _prompt(label: str):
    return (
        "integrated_multimodal_description:\n"
        f"[Shot 1] {label}.\n"
        "overall_soundscape:\nRoom.\nnon_diegetic_music:\nNone."
    )


def main():
    finite = _load_package(Path(__file__).resolve().parents[1])
    planner_schema = finite.MiniMaxH3FiniteSegmentExpansion.define_schema()
    sampler_schema = finite.MiniMaxH3FiniteSegmentSampler.define_schema()
    planner_inputs = {item.id for item in planner_schema.inputs}
    assert not planner_inputs.intersection({"model", "clip", "vae", "audio_vae", "sampler", "sigmas", "seed"})
    assert sampler_schema.enable_expand is True
    sampler_input_ids = {item.id for item in sampler_schema.inputs}
    assert "increment_seed" not in sampler_input_ids
    assert "gradient_temporal_mask" not in sampler_input_ids
    assert "continuation_mode" not in sampler_input_ids

    prompts = "\n--- SEGMENT ---\n".join(
        [_prompt("First"), _prompt("Second"), _prompt("Third")]
    )
    planned = finite.MiniMaxH3FiniteSegmentExpansion.execute(
        plan=_plan(), segment_prompts=prompts, segment_count=3,
        overlap_frames=48, inject_continuity_instruction=True,
    )
    finite_plan = planned[0]
    assert planned[1] == 39
    assert "performs no sampling" in planned[2]
    assert "carried latent continuation" not in finite_plan["prompts"][0]
    assert "carried latent continuation" in finite_plan["prompts"][1]

    output = finite.MiniMaxH3FiniteSegmentSampler.execute(
        model=object(), clip=object(), vae=object(), audio_vae=object(),
        finite_plan=finite_plan, sampler=object(),
        sigmas=torch.linspace(1.0, 0.0, 5), seed=100,
        continue_audio_latent=True, ref_image_size="match",
    )
    graph = output.expand
    by_type = {}
    for node_id, node in graph.items():
        by_type.setdefault(node["class_type"], []).append((node_id, node["inputs"]))
    assert len(by_type["MiniMaxH3TimelineEncoder"]) == 3
    assert len(by_type["MiniMaxH3FiniteLatentContinuation"]) == 3
    assert len(by_type["SamplerCustomAdvanced"]) == 3
    assert len(by_type["MiniMaxH3FiniteSegmentFinalize"]) == 3
    assert len(by_type["ImageBatch"]) == 2
    assert len(by_type["AudioConcat"]) == 2

    encoders = sorted(by_type["MiniMaxH3TimelineEncoder"])
    assert [node[1]["plan"]["prompt_index"] for node in encoders] == [1, 2, 3]
    assert [len(node[1]["plan"]["timeline"]["images"]) for node in encoders] == [2, 1, 1]
    assert [len(node[1]["plan"]["timeline"]["audios"]) for node in encoders] == [1, 1, 0]
    noises = sorted(by_type["RandomNoise"])
    assert [node[1]["noise_seed"] for node in noises] == [100, 100, 100]
    continuations = sorted(by_type["MiniMaxH3FiniteLatentContinuation"])
    assert "previous_latent" not in continuations[0][1]
    assert "previous_latent" in continuations[1][1]
    assert all("gradient_temporal_mask" not in item[1] for item in continuations)
    assert all("continuation_mode" not in item[1] for item in continuations)
    assert all(item[1]["trim_audio_head"] is False for item in by_type["MiniMaxH3FiniteSegmentFinalize"])
    assert len(by_type["MiniMaxH3FiniteAudioTrimTail"]) == 2
    assert "Drift-Control AV 39-frame" in output[3]
    assert "Soft AV half-cosine release" in output[3]
    assert "all segments use seed 100" in output[3]
    assert all(
        node["class_type"] not in {
            "Loop", "LoopVariable", "CloseLoop", "MiniMaxH3LoopPromptSelector",
            "MiniMaxH3LoopLatentGuide", "MiniMaxH3LoopSegmentFinalize",
        }
        for node in graph.values()
    )

    for steps in (8, 20):
        drift_output = finite.MiniMaxH3FiniteSegmentSampler.execute(
            model=object(), clip=object(), vae=object(), audio_vae=object(),
            finite_plan=finite_plan, sampler=object(),
            sigmas=torch.linspace(1.0, 0.0, steps + 1),
            seed=100, continue_audio_latent=True, ref_image_size="match",
        )
        drift_continuations = [
            node["inputs"] for node in drift_output.expand.values()
            if node["class_type"] == "MiniMaxH3FiniteLatentContinuation"
        ]
        assert len(drift_continuations) == 3
        assert all("continuation_mode" not in item for item in drift_continuations)
        drift_finalizers = [
            node["inputs"] for node in drift_output.expand.values()
            if node["class_type"] == "MiniMaxH3FiniteSegmentFinalize"
        ]
        assert all(item["trim_audio_head"] is False for item in drift_finalizers)
        assert sum(
            node["class_type"] == "MiniMaxH3FiniteAudioTrimTail"
            for node in drift_output.expand.values()
        ) == 2
        assert f"adapted to {steps} sampling steps" in drift_output[3]
        assert "Soft AV half-cosine release" in drift_output[3]

    short_planned = finite.MiniMaxH3FiniteSegmentExpansion.execute(
        plan=_plan(), segment_prompts=prompts, segment_count=3,
        overlap_frames=24, inject_continuity_instruction=True,
    )
    assert short_planned[1] == 22
    short_output = finite.MiniMaxH3FiniteSegmentSampler.execute(
        model=object(), clip=object(), vae=object(), audio_vae=object(),
        finite_plan=short_planned[0], sampler=object(),
        sigmas=torch.linspace(1.0, 0.0, 5), seed=100,
        continue_audio_latent=True, ref_image_size="match",
    )
    assert "Drift-Control AV 22-frame" in short_output[3]
    assert all(
        node["inputs"]["overlap_frames"] == 22
        for node in short_output.expand.values()
        if node["class_type"] in {
            "MiniMaxH3FiniteLatentContinuation",
            "MiniMaxH3FiniteSegmentFinalize",
            "MiniMaxH3FiniteAudioTrimTail",
        }
    )

    sample_rate = 16000
    accumulated = {
        "waveform": torch.arange(sample_rate * 4, dtype=torch.float32).reshape(1, 1, -1),
        "sample_rate": sample_rate,
    }
    tail_trimmed = finite.MiniMaxH3FiniteAudioTrimTail.execute(
        accumulated, overlap_frames=48,
    )[0]
    assert tail_trimmed["waveform"].shape[-1] == sample_rate * 4 - round(39 / 24 * sample_rate)
    print("finite planning/sampling smoke test: PASS")


if __name__ == "__main__":
    main()
