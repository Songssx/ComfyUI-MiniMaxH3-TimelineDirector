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


def _long_reference_plan():
    return {
        "type": "MINIMAX_H3_TIMELINE_PLAN", "version": 1,
        "width": 1280, "height": 736, "generation_seconds": 10.0,
        "length": 243, "prompt_index": None, "segment_count": 0,
        "timeline": {
            "selection": {"start": 0.0, "duration": 10.0},
            "videoAudioEnabled": True,
            "videoClips": [{
                "id": "v1", "file": "minute.mp4", "name": "minute.mp4",
                "start": 0.0, "duration": 60.0, "trimStart": 2.0,
                "sourceDuration": 62.0, "hasAudio": True,
                "referenceMode": "guide",
            }],
            "images": [{"id": "p1", "file": "identity.png"}],
            "audios": [{
                "id": "a1", "file": "speech.wav", "name": "speech.wav",
                "trimStart": 0.0, "duration": 60.0,
            }],
            "segmentConfig": {"count": 0, "segments": []},
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
    long_schema = finite.MiniMaxH3LongReferenceSegmentPlan.define_schema()
    planner_inputs = {item.id for item in planner_schema.inputs}
    assert not planner_inputs.intersection({"model", "clip", "vae", "audio_vae", "sampler", "sigmas", "seed"})
    assert sampler_schema.enable_expand is True
    sampler_input_ids = {item.id for item in sampler_schema.inputs}
    assert "increment_seed" not in sampler_input_ids
    assert "gradient_temporal_mask" not in sampler_input_ids
    assert "continuation_mode" not in sampler_input_ids
    assert {item.id for item in long_schema.inputs} == {
        "plan", "prompt", "overlap_frames", "slice_reference_audio",
    }

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

    shared_prompt = _prompt("Replace the target person using Picture 1 and Video 1")
    auto_planned = finite.MiniMaxH3LongReferenceSegmentPlan.execute(
        plan=_long_reference_plan(), prompt=shared_prompt,
        overlap_frames=48, slice_reference_audio=True,
    )
    auto_plan = auto_planned[0]
    assert auto_planned[1:3] == (7, 39)
    assert auto_plan["version"] == 2
    assert auto_plan["mode"] == "long_reference_auto_segments"
    assert auto_plan["segment_frames"] == 243
    assert auto_plan["stride_frames"] == 204
    assert auto_plan["assembled_frames_before_trim"] == 1467
    assert auto_plan["trim_tail_frames"] == 27
    assert auto_plan["target_output_frames"] == 1440
    assert auto_plan["prompts"] == [shared_prompt] * 7
    assert len(auto_plan["segment_plans"]) == 7
    for index, segment_plan in enumerate(auto_plan["segment_plans"]):
        segment_timeline = segment_plan["timeline"]
        segment_clip = segment_timeline["videoClips"][0]
        assert segment_clip["referenceMode"] == "guide"
        assert segment_clip["start"] == 0.0
        assert segment_clip["trimStart"] == 2.0 + index * 204 / 24
        assert segment_plan["length"] == 243
        assert segment_timeline["selection"] == {"start": 0.0, "duration": 243 / 24}
        assert segment_timeline["segmentConfig"] == {"count": 0, "segments": []}
        assert segment_timeline["audios"][0]["trimStart"] == index * 204 / 24
    assert auto_plan["segment_plans"][-1]["timeline"]["videoClips"][0]["duration"] == 9.0
    assert auto_plan["segment_plans"][-1]["timeline"]["audios"][0]["duration"] == 9.0

    repeat_planned = finite.MiniMaxH3LongReferenceSegmentPlan.execute(
        plan=_long_reference_plan(), prompt=shared_prompt,
        overlap_frames=48, slice_reference_audio=False,
    )[0]
    assert all(
        item["timeline"]["audios"][0]["trimStart"] == 0.0
        and item["timeline"]["audios"][0]["duration"] == 60.0
        for item in repeat_planned["segment_plans"]
    )

    editable_source = _long_reference_plan()
    editable_source["timeline"]["videoClips"][0]["referenceMode"] = "edit"
    editable_plan = finite.MiniMaxH3LongReferenceSegmentPlan.execute(
        plan=editable_source, prompt=shared_prompt,
        overlap_frames=48, slice_reference_audio=True,
    )[0]
    assert editable_plan["reference_mode"] == "edit"
    assert all(
        item["timeline"]["videoClips"][0]["referenceMode"] == "edit"
        for item in editable_plan["segment_plans"]
    )

    short_source = _long_reference_plan()
    short_source["generation_seconds"] = 5.0
    short_source["length"] = 124
    short_duration_plan = finite.MiniMaxH3LongReferenceSegmentPlan.execute(
        plan=short_source, prompt=shared_prompt,
        overlap_frames=24, slice_reference_audio=True,
    )[0]
    assert short_duration_plan["segment_frames"] == 124
    assert all(
        item["generation_seconds"] == 124 / 24
        for item in short_duration_plan["segment_plans"]
    )

    audio_only_source = _long_reference_plan()
    audio_only_source["timeline"]["videoClips"] = []
    audio_only_plan = finite.MiniMaxH3LongReferenceSegmentPlan.execute(
        plan=audio_only_source, prompt=shared_prompt,
        overlap_frames=48, slice_reference_audio=True,
    )[0]
    assert audio_only_plan["duration_source"] == "audio"
    assert audio_only_plan["source_duration_seconds"] == 60.0
    assert audio_only_plan["target_output_frames"] == 1440
    assert audio_only_plan["segment_count"] == 7
    assert audio_only_plan["reference_mode"] == "none"
    assert all(
        not item["timeline"]["videoClips"]
        and item["timeline"]["images"] == [{"id": "p1", "file": "identity.png"}]
        for item in audio_only_plan["segment_plans"]
    )
    assert [
        item["timeline"]["audios"][0]["trimStart"]
        for item in audio_only_plan["segment_plans"]
    ] == [index * 204 / 24 for index in range(7)]

    mixed_length_source = _long_reference_plan()
    mixed_length_source["timeline"]["videoClips"][0]["duration"] = 30.0
    mixed_length_plan = finite.MiniMaxH3LongReferenceSegmentPlan.execute(
        plan=mixed_length_source, prompt=shared_prompt,
        overlap_frames=48, slice_reference_audio=True,
    )[0]
    assert mixed_length_plan["duration_source"] == "video_and_audio"
    assert mixed_length_plan["video_duration_seconds"] == 30.0
    assert mixed_length_plan["audio_duration_seconds"] == 60.0
    assert mixed_length_plan["source_duration_seconds"] == 60.0
    assert mixed_length_plan["segment_count"] == 7
    # Segment four intersects only the remaining 4.5 seconds of video; later
    # segments remain image/audio-driven instead of freezing or looping it.
    assert mixed_length_plan["segment_plans"][3]["timeline"]["videoClips"][0]["duration"] == 4.5
    assert all(
        not item["timeline"]["videoClips"]
        for item in mixed_length_plan["segment_plans"][4:]
    )

    empty_source = _long_reference_plan()
    empty_source["timeline"]["videoClips"] = []
    empty_source["timeline"]["audios"] = []
    try:
        finite.MiniMaxH3LongReferenceSegmentPlan.execute(
            plan=empty_source, prompt=shared_prompt,
            overlap_frames=48, slice_reference_audio=True,
        )
    except ValueError as error:
        assert "timeline video or standalone audio" in str(error)
    else:
        raise AssertionError("long-media planning must reject a plan with no timed media")

    auto_output = finite.MiniMaxH3FiniteSegmentSampler.execute(
        model=object(), clip=object(), vae=object(), audio_vae=object(),
        finite_plan=auto_plan, sampler=object(),
        sigmas=torch.linspace(1.0, 0.0, 5), seed=100,
        continue_audio_latent=True, ref_image_size="match",
    )
    auto_nodes = list(auto_output.expand.values())
    auto_encoders = [
        item for item in auto_nodes if item["class_type"] == "MiniMaxH3TimelineEncoder"
    ]
    assert len(auto_encoders) == 7
    assert [item["inputs"]["prompt"] for item in auto_encoders] == [shared_prompt] * 7
    assert [
        item["inputs"]["plan"]["timeline"]["videoClips"][0]["trimStart"]
        for item in auto_encoders
    ] == [2.0 + index * 204 / 24 for index in range(7)]
    output_trims = [
        item for item in auto_nodes if item["class_type"] == "MiniMaxH3FiniteOutputTrim"
    ]
    assert len(output_trims) == 1
    assert output_trims[0]["inputs"]["output_frames"] == 1440
    assert "identical prompt" in auto_planned[3]
    assert "final 27 excess tail frames" in auto_output[3]
    assert "source-media duration (1440 frames)" in auto_output[3]

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
    print("finite planning/sampling smoke test: PASS")


if __name__ == "__main__":
    main()
