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

    # In two-stage mode, enabling an embedded reference-video soundtrack turns
    # it into the same zero-denoise/final-master path used by explicit locked
    # audio. Disabling video audio leaves sound generation to H3.
    video_plan = _plan()
    video_plan["timeline"]["videoAudioEnabled"] = True
    video_plan["timeline"]["videoClips"] = [{
        "id": "v1", "file": "reference.mp4", "start": 0.0,
        "trimStart": 1.25, "duration": 8.0, "hasAudio": True,
    }]
    video_finite = {
        "type": "minimax_h3_finite_segment_plan", "version": 4,
        "mode": "single_segment", "source_plan": video_plan,
        "segment_count": 1, "segment_plans": [video_plan],
        "prompts": [_prompt("Video")], "second_pass": True,
        "overlap_frames": 0, "segment_overlaps": [0],
        "segment_lengths": [192], "target_output_frames": 192,
    }
    automatic_video_lock = finite._finite_locked_audio_asset(video_finite)
    assert automatic_video_lock["lockKind"] == "timeline_video_audio"
    video_finite["second_pass"] = False
    assert finite._finite_locked_audio_asset(video_finite)["lockKind"] == "timeline_video_audio"
    one_pass_video_output = finite.MiniMaxH3FiniteSegmentSampler.execute(
        model=object(), clip=object(), vae=object(), audio_vae=object(),
        finite_plan=video_finite, sampler=object(),
        sigmas=torch.linspace(1.0, 0.0, 5), seed=100,
        continue_audio_latent=True, ref_image_size="match",
    )
    one_pass_video_types = [
        node["class_type"] for node in one_pass_video_output.expand.values()
    ]
    assert "SamplerCustomAdvanced" in one_pass_video_types
    assert "MiniMaxH3LockedAudioSlice" in one_pass_video_types
    assert "MiniMaxH3LockAudioLatent" in one_pass_video_types
    assert "MiniMaxH3LockedAudioMaster" in one_pass_video_types
    assert "AudioConcat" not in one_pass_video_types
    video_plan["timeline"]["videoAudioEnabled"] = False
    assert finite._finite_locked_audio_asset(video_finite) is None
    assert finite._finite_video_audio_muted(video_finite) is True
    muted_output = finite.MiniMaxH3FiniteSegmentSampler.execute(
        model=object(), clip=object(), vae=object(), audio_vae=object(),
        finite_plan=video_finite, sampler=object(),
        sigmas=torch.linspace(1.0, 0.0, 5), seed=100,
        continue_audio_latent=True, ref_image_size="match",
    )
    muted_types = [node["class_type"] for node in muted_output.expand.values()]
    assert "MiniMaxH3SilentAudioSlice" in muted_types
    assert "MiniMaxH3LockAudioLatent" in muted_types
    assert "MiniMaxH3SilentAudioMaster" in muted_types
    assert "AudioConcat" not in muted_types
    assert "final output is silent" in muted_output[3]

    video_finite["second_pass"] = True
    video_plan["timeline"]["videoAudioEnabled"] = True
    assert finite._finite_video_audio_muted(video_finite) is False

    original_selflift_settings = finite._selflift_settings
    finite._selflift_settings = lambda *_args, **_kwargs: {
        "transition_step": 2, "lowres_scale": 0.5, "rho": 0.0,
        "w_min": 0.5, "w_max": 1.0, "upscaler_model": "test.safetensors",
    }
    try:
        video_output = finite.MiniMaxH3FiniteSegmentSampler.execute(
            model=object(), clip=object(), vae=object(), audio_vae=object(),
            finite_plan=video_finite, sampler=object(),
            sigmas=torch.linspace(1.0, 0.0, 5), seed=100,
            continue_audio_latent=True, ref_image_size="match",
        )
    finally:
        finite._selflift_settings = original_selflift_settings
    video_types = [node["class_type"] for node in video_output.expand.values()]
    assert "MiniMaxH3LockedAudioSlice" in video_types
    assert "MiniMaxH3LockAudioLatent" in video_types
    assert "MiniMaxH3LockedAudioMaster" in video_types
    assert "AudioConcat" not in video_types
    assert "exact edited timeline waveform" in video_output[3]

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
    assert "ImageBatch" not in by_type
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
    finalizers = sorted(by_type["MiniMaxH3FiniteSegmentFinalize"])
    assert "accumulated_images" not in finalizers[0][1]
    assert all("accumulated_images" in item[1] for item in finalizers[1:])
    assert all(item[1]["trim_audio_head"] is False for item in finalizers)
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

    # The preceding segment owns the visual overlap: keep its complete tail
    # and remove the matching opening frames from the incoming segment.
    preceding = torch.ones((8, 1, 1, 1), dtype=torch.float32)
    incoming = torch.full((8, 1, 1, 1), 2.0, dtype=torch.float32)
    joined = finite.MiniMaxH3FiniteSegmentFinalize.execute(
        {"samples": torch.zeros(1)}, incoming, iteration=1,
        overlap_frames=5, accumulated_images=preceding,
    )[1]
    assert joined.shape[0] == 11
    assert torch.all(joined[:8] == 1)
    assert torch.all(joined[8:] == 2)

    images = torch.arange(1467, dtype=torch.float32).reshape(1467, 1, 1, 1)
    long_audio = {
        "waveform": torch.zeros((1, 2, sample_rate * 63)),
        "sample_rate": sample_rate,
    }
    exact_images, exact_audio = finite.MiniMaxH3FiniteOutputTrim.execute(
        images, long_audio, output_frames=1440,
    )[:2]
    assert exact_images.shape[0] == 1440
    assert exact_images[-1].item() == 1439
    assert exact_audio["waveform"].shape[-1] == sample_rate * 60

    # Native Start/End Loop integration exposes one segment at a time and
    # carries only the state required by the following iteration.
    loop_classes = {
        "MiniMaxH3FiniteLoopInitialize",
        "MiniMaxH3FiniteLoopSegment",
        "MiniMaxH3FiniteLoopPrepare",
        "MiniMaxH3FiniteLoopAccumulate",
        "MiniMaxH3FiniteLoopOutput",
    }
    assert loop_classes.issubset(sys.modules["minimax_h3_finite_smoke"].NODE_CLASS_MAPPINGS)
    loop_state, loop_count = finite.MiniMaxH3FiniteLoopInitialize.execute(finite_plan)
    assert loop_count == 3 and loop_state["next_iteration"] == 0
    selected = finite.MiniMaxH3FiniteLoopSegment.execute(finite_plan, 1)
    assert selected[1] == finite_plan["prompts"][1]
    assert selected[2] == 39

    prepared = finite.MiniMaxH3FiniteLoopPrepare.execute(
        finite_plan=finite_plan, loop_state=loop_state,
        segment_plan=finite._finite_plan_for_segment(finite_plan, 1),
        positive=object(), target_latent=object(), model=object(),
        sigmas=torch.linspace(1.0, 0.0, 5), vae=object(), audio_vae=object(),
        iteration_index=0, continue_audio_latent=True,
    )
    assert any(
        node["class_type"] == "MiniMaxH3FiniteLatentContinuation"
        for node in prepared.expand.values()
    )

    segment_images = torch.ones((60, 1, 1, 1), dtype=torch.float32)
    segment_audio = {
        "waveform": torch.zeros((1, 2, sample_rate * 3)),
        "sample_rate": sample_rate,
    }
    for index in range(3):
        loop_state, merged_loop_images, merged_loop_audio = finite.MiniMaxH3FiniteLoopAccumulate.execute(
            finite_plan=finite_plan, loop_state=loop_state,
            sampled_latent={"samples": torch.tensor(float(index))},
            images=segment_images * (index + 1), audio=segment_audio,
            iteration_index=index, continue_audio_latent=True,
        )
    assert loop_state["next_iteration"] == 3
    assert merged_loop_images.shape[0] == 60 + 2 * (60 - 39)
    assert merged_loop_audio["waveform"].shape[-1] > 0
    final_loop = finite.MiniMaxH3FiniteLoopOutput.execute(loop_state)
    assert final_loop[1].shape[0] == merged_loop_images.shape[0]
    assert "Native ComfyUI Loop completed 3" in final_loop[3]
    print("finite planning/sampling smoke test: PASS")


if __name__ == "__main__":
    main()
