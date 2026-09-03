"""Plugin-owned finite MiniMax H3 long-video planning and sampling."""

from __future__ import annotations

import copy
import json
import math
import re

from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder

from .experimental_latent_guide import (
    _apply_linear_temporal_noise_mask,
    _valid_guide_frames,
)
from .drift_control_av import (
    drift_control_step_count,
    install_drift_control_av_model,
)
from .minimax_h3_timeline_director import (
    TimelinePlan,
    _aligned_h3_length,
    _require_timeline_plan,
    _timeline_for_prompt_index,
)

H3_FPS = 24
FiniteSegmentPlan = io.Custom("MINIMAX_H3_FINITE_SEGMENT_PLAN")


def _parse_segment_prompts(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        raise ValueError("Segment prompts cannot be empty")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        parsed = parsed.get("segments")
    if isinstance(parsed, list):
        prompts = [str(item).strip() for item in parsed if str(item).strip()]
    else:
        prompts = [
            part.strip()
            for part in re.split(r"(?m)^\s*---\s*SEGMENT\s*---\s*$", text)
            if part.strip()
        ]
    if not prompts:
        raise ValueError("No segment prompts were parsed; use a JSON array or --- SEGMENT --- separators")
    return prompts


def _inject_continuity_instruction(prompt: str, overlap_frames: int) -> tuple[str, bool]:
    duration = overlap_frames / H3_FPS
    instruction = (
        f" The opening 00:00.000-00:{duration:06.3f} is a carried latent continuation "
        "from the preceding segment. Describe this opening as the preceding segment's "
        "final shot, preserving character positions, environment, motion, camera path, "
        "lighting, color, and sound before introducing new action."
    )
    for field in ("integrated_multimodal_description:", "detailed_description:"):
        field_index = prompt.find(field)
        if field_index < 0:
            continue
        shot_index = prompt.find("[Shot 1]", field_index + len(field))
        if shot_index >= 0:
            insert_at = shot_index + len("[Shot 1]")
            return prompt[:insert_at] + instruction + prompt[insert_at:], True
    return prompt, False


def _plan_for_segment(plan, segment_number: int):
    source = _require_timeline_plan(plan)
    if source.get("prompt_index") is not None:
        raise ValueError("Finite segments require the complete material plan; leave Prompt Index disconnected")
    timeline, selected, configured_count = _timeline_for_prompt_index(
        source["timeline"], segment_number
    )
    result = copy.deepcopy(source)
    result["timeline"] = timeline
    result["prompt_index"] = selected
    result["segment_count"] = configured_count
    return result


def _finite_plan_for_segment(finite: dict, segment_number: int):
    segment_plans = finite.get("segment_plans")
    if isinstance(segment_plans, list):
        index = int(segment_number) - 1
        if index < 0 or index >= len(segment_plans):
            raise ValueError(f"Segment {segment_number} has no material plan")
        return copy.deepcopy(_require_timeline_plan(segment_plans[index]))
    return _plan_for_segment(finite["source_plan"], segment_number)


def _synchronized_audio_assets(
    assets: list, source_offset_seconds: float, window_seconds: float,
) -> list[dict]:
    """Slice long standalone audio on the same clock as the source video."""

    sliced: list[dict] = []
    for raw in assets:
        if not isinstance(raw, dict) or not raw.get("file"):
            continue
        asset = copy.deepcopy(raw)
        base_start = max(0.0, float(asset.get("trimStart") or 0.0))
        base_duration = max(0.0, float(asset.get("duration") or 0.0))
        if base_duration <= source_offset_seconds:
            continue
        asset["trimStart"] = base_start + source_offset_seconds
        asset["duration"] = min(window_seconds, base_duration - source_offset_seconds)
        sliced.append(asset)
    return sliced


def _prepare_long_reference_plan(
    plan, prompt: str, overlap_frames: int, slice_reference_audio: bool,
):
    """Build per-segment video references without materializing clips."""

    source = _require_timeline_plan(plan)
    if source.get("prompt_index") is not None:
        raise ValueError(
            "Long reference segmentation requires the complete material plan; "
            "leave Prompt Index disconnected"
        )
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("The shared prompt cannot be empty")

    timeline = source["timeline"]
    clips = [
        item for item in timeline.get("videoClips", [])
        if isinstance(item, dict) and item.get("file")
    ]
    if len(clips) > 1:
        raise ValueError(
            "Long reference segmentation currently accepts at most one timeline video"
        )
    clip = clips[0] if clips else None
    audio_assets = [
        item for item in timeline.get("audios", [])
        if isinstance(item, dict) and item.get("file")
    ]
    video_duration = (
        max(0.0, float(clip.get("duration") or 0.0)) if clip else 0.0
    )
    audio_duration = max(
        (max(0.0, float(item.get("duration") or 0.0)) for item in audio_assets),
        default=0.0,
    )
    source_duration = max(video_duration, audio_duration)
    total_frames = max(0, round(source_duration * H3_FPS))
    if total_frames < 5:
        raise ValueError(
            "Upload a timeline video or standalone audio containing at least 5 frames of time"
        )

    segment_seconds = float(source.get("generation_seconds") or 0.0)
    if segment_seconds <= 0:
        raise ValueError(
            "The Material Planner generation duration must be greater than zero"
        )
    segment_frames = _aligned_h3_length(segment_seconds)
    actual_overlap = _valid_guide_frames(int(overlap_frames))
    if actual_overlap >= segment_frames:
        raise ValueError(
            f"The actual {actual_overlap}-frame overlap must be shorter than the "
            f"{segment_frames}-frame segment"
        )
    stride_frames = segment_frames - actual_overlap
    segment_count = 1 + max(
        0, math.ceil((total_frames - segment_frames) / stride_frames)
    )
    starts = [index * stride_frames for index in range(segment_count)]
    assembled_frames = segment_frames + (segment_count - 1) * stride_frames
    trim_tail_frames = max(0, assembled_frames - total_frames)

    base_trim = max(0.0, float(clip.get("trimStart") or 0.0)) if clip else 0.0
    video_frames = max(0, round(video_duration * H3_FPS))
    segment_plans = []
    for start_frame in starts:
        available_frames = min(segment_frames, total_frames - start_frame)
        window_seconds = available_frames / H3_FPS
        segment_timeline = copy.deepcopy(timeline)
        if clip and start_frame < video_frames:
            available_video_frames = min(
                segment_frames, video_frames - start_frame
            )
            segment_clip = copy.deepcopy(clip)
            segment_clip["start"] = 0.0
            segment_clip["trimStart"] = base_trim + start_frame / H3_FPS
            segment_clip["duration"] = available_video_frames / H3_FPS
            # Preserve the purpose selected in the Material Planner. Character-
            # swap workflows should select Editable Reference there; Fixed Guide
            # and Boundary Only intentionally retain their anchoring behavior.
            segment_timeline["videoClips"] = [segment_clip]
        else:
            # The longest standalone audio may outlive the reference video, or
            # an audio-driven digital-human workflow may contain no video at all.
            # Do not repeat/freeze a shorter video into those later windows.
            segment_timeline["videoClips"] = []
        segment_timeline["selection"] = {
            "start": 0.0,
            "duration": segment_frames / H3_FPS,
        }
        segment_timeline["segmentConfig"] = {"count": 0, "segments": []}
        if slice_reference_audio:
            segment_timeline["audios"] = _synchronized_audio_assets(
                list(timeline.get("audios") or []),
                start_frame / H3_FPS,
                window_seconds,
            )

        segment_plan = copy.deepcopy(source)
        segment_plan["timeline"] = segment_timeline
        segment_plan["generation_seconds"] = segment_frames / H3_FPS
        segment_plan["length"] = segment_frames
        segment_plan["prompt_index"] = None
        segment_plan["segment_count"] = segment_count
        segment_plans.append(segment_plan)

    return {
        "type": "minimax_h3_finite_segment_plan",
        "version": 2,
        "mode": "long_reference_auto_segments",
        "source_plan": copy.deepcopy(source),
        "segment_plans": segment_plans,
        "prompts": [prompt] * segment_count,
        "segment_count": segment_count,
        "requested_overlap_frames": int(overlap_frames),
        "overlap_frames": actual_overlap,
        "segment_frames": segment_frames,
        "stride_frames": stride_frames,
        "assembled_frames_before_trim": assembled_frames,
        "trim_tail_frames": trim_tail_frames,
        "target_output_frames": total_frames,
        "source_duration_seconds": source_duration,
        "reference_mode": (
            str(clip.get("referenceMode") or "guide") if clip else "none"
        ),
        "video_duration_seconds": video_duration,
        "audio_duration_seconds": audio_duration,
        "duration_source": (
            "video_and_audio"
            if video_duration > 0 and audio_duration > 0
            else "video" if video_duration > 0 else "audio"
        ),
        "slice_reference_audio": bool(slice_reference_audio),
    }


def _prepare_finite_plan(
    plan,
    segment_prompts: str,
    segment_count: int,
    overlap_frames: int,
    inject_continuity: bool,
):
    source = _require_timeline_plan(plan)
    count = int(segment_count)
    configured_count = int(source.get("segment_count") or 0)
    if configured_count > 0 and configured_count != count:
        raise ValueError(
            f"The material planner has {configured_count} segments but finite expansion requests {count}; keep them identical"
        )
    prompts = _parse_segment_prompts(segment_prompts)
    if len(prompts) != count:
        raise ValueError(
            f"Finite expansion requests {count} segments but parsed {len(prompts)} prompts; keep them identical"
        )
    actual_overlap = _valid_guide_frames(int(overlap_frames))
    prepared = []
    for index, prompt in enumerate(prompts):
        if index > 0 and inject_continuity:
            prompt, injected = _inject_continuity_instruction(prompt, actual_overlap)
            if not injected:
                raise ValueError(
                    f"Segment {index + 1} has no [Shot 1] in the standard H3 fields; continuity instructions cannot be injected"
                )
        prepared.append(prompt)
    return {
        "type": "minimax_h3_finite_segment_plan",
        "version": 1,
        "source_plan": copy.deepcopy(source),
        "prompts": prepared,
        "segment_count": count,
        "requested_overlap_frames": int(overlap_frames),
        "overlap_frames": actual_overlap,
    }


def _require_finite_plan(value):
    if not isinstance(value, dict) or value.get("type") != "minimax_h3_finite_segment_plan":
        raise ValueError("finite_plan must come from MiniMax H3 Finite Segment Expansion")
    count = int(value.get("segment_count") or 0)
    prompts = value.get("prompts")
    if count < 1 or not isinstance(prompts, list) or len(prompts) != count:
        raise ValueError("The finite segment plan is incomplete; run Finite Segment Expansion again")
    segment_plans = value.get("segment_plans")
    if segment_plans is not None and (
        not isinstance(segment_plans, list) or len(segment_plans) != count
    ):
        raise ValueError("The long reference plan has incomplete per-segment materials")
    return value


class MiniMaxH3FiniteSegmentExpansion(io.ComfyNode):
    """Validate prompts/media assignments and produce a reusable finite plan."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteSegmentExpansion",
            display_name="MiniMax H3 Finite Segment Expansion",
            category="MiniMax H3/Long Video",
            description=(
                "Parse prompts, validate segment counts, match per-segment media, and build a finite plan. "
                "This node performs no model loading, scheduling, or sampling."
            ),
            inputs=[
                TimelinePlan.Input("plan", display_name="Material Plan"),
                io.String.Input("segment_prompts", multiline=True),
                io.Int.Input("segment_count", display_name="Segment Count", default=3, min=1, max=12),
                io.Int.Input(
                    "overlap_frames", display_name="Overlap Frames", default=22,
                    min=1, max=362, tooltip="Rounded down to a valid 1 or 5/22/39/56… frame count.",
                ),
                io.Boolean.Input(
                    "inject_continuity_instruction", display_name="Inject Opening Continuity", default=True,
                ),
            ],
            outputs=[
                FiniteSegmentPlan.Output(display_name="Finite Segment Plan"),
                io.Int.Output(display_name="Actual Overlap Frames"),
                io.String.Output(display_name="Planning Status"),
            ],
        )

    @classmethod
    def execute(
        cls, plan, segment_prompts, segment_count, overlap_frames,
        inject_continuity_instruction,
    ):
        finite = _prepare_finite_plan(
            plan, segment_prompts, segment_count, overlap_frames,
            bool(inject_continuity_instruction),
        )
        overlap = finite["overlap_frames"]
        status = (
            f"Planned {finite['segment_count']} segments; actual overlap is {overlap} frames "
            f"({overlap / H3_FPS:.3f}s). This node performs no sampling."
        )
        return io.NodeOutput(finite, overlap, status)


class MiniMaxH3LongReferenceSegmentPlan(io.ComfyNode):
    """Automatically slice one long reference for a shared prompt."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LongReferenceSegmentPlan",
            display_name="MiniMax H3 Long Reference Auto Segmentation",
            category="MiniMax H3/Long Video",
            description=(
                "Use the Material Planner generation duration to split long reference media. "
                "Audio-only plans follow the longest standalone audio; video-plus-audio "
                "plans follow whichever is longer. Video purpose is preserved, one prompt "
                "is reused, and standalone audio can be sliced on the same clock."
            ),
            inputs=[
                TimelinePlan.Input("plan", display_name="Material Plan"),
                io.String.Input("prompt", multiline=True),
                io.Int.Input(
                    "overlap_frames", display_name="Overlap Frames", default=48,
                    min=1, max=362,
                    tooltip="Rounded down to a valid 1 or 5/22/39/56… frame count.",
                ),
                io.Boolean.Input(
                    "slice_reference_audio", display_name="Slice Standalone Audio", default=True,
                    tooltip=(
                        "On: long standalone audio follows every video slice for lip sync. "
                        "Off: each segment reuses the complete standalone audio as a timbre reference."
                    ),
                ),
            ],
            outputs=[
                FiniteSegmentPlan.Output(display_name="Finite Segment Plan"),
                io.Int.Output(display_name="Segment Count"),
                io.Int.Output(display_name="Actual Overlap Frames"),
                io.String.Output(display_name="Planning Status"),
            ],
        )

    @classmethod
    def execute(
        cls, plan, prompt, overlap_frames, slice_reference_audio=True,
    ):
        finite = _prepare_long_reference_plan(
            plan, prompt, overlap_frames, bool(slice_reference_audio),
        )
        purpose = {
            "guide": "Fixed Guide",
            "edit": "Editable Reference",
            "boundary": "Boundary Only",
            "none": "audio-driven",
        }.get(finite["reference_mode"], finite["reference_mode"])
        status = (
            f"Split the {finite['source_duration_seconds']:.3f}s longest media span "
            f"({finite['duration_source']}) into "
            f"{finite['segment_count']} overlapping {purpose} segments using the "
            f"Material Planner duration; each segment generates "
            f"{finite['segment_frames']} frames, advances "
            f"{finite['stride_frames']} frames, and reuses the identical prompt. "
            f"Actual overlap is {finite['overlap_frames']} frames; the final "
            f"{finite['trim_tail_frames']} excess tail frames will be removed."
        )
        return io.NodeOutput(
            finite, finite["segment_count"], finite["overlap_frames"], status
        )


class MiniMaxH3FiniteLatentContinuation(io.ComfyNode):
    """Internal finite-graph helper that carries the previous AV latent tail."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteLatentContinuation",
            display_name="MiniMax H3 Finite Latent Continuation (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("target_latent"),
                io.Int.Input("iteration", force_input=True),
                io.Int.Input("overlap_frames", default=22, min=1, max=362),
                io.Boolean.Input("continue_audio_latent", default=True),
                io.Model.Input("model"),
                io.Sigmas.Input("sigmas"),
                io.Latent.Input("previous_latent", optional=True),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(display_name="Target Latent"),
                io.Int.Output(display_name="Actual Overlap Frames"),
                io.Model.Output(display_name="Sampling Model"),
            ],
        )

    @classmethod
    def execute(
        cls, positive, target_latent, iteration, overlap_frames,
        continue_audio_latent, model, sigmas, previous_latent=None,
    ):
        actual_overlap = _valid_guide_frames(int(overlap_frames))
        if int(iteration) <= 0:
            return io.NodeOutput(positive, target_latent, actual_overlap, model)
        if previous_latent is None:
            raise ValueError("Segment 2 and later require the previous sampled latent")
        masked_target, details = _apply_linear_temporal_noise_mask(
            target_latent=target_latent,
            source_latent=previous_latent,
            guide_frames=actual_overlap,
            include_audio=bool(continue_audio_latent),
            gradient=False,
            audio_soft_release=bool(continue_audio_latent),
        )
        patched_model = install_drift_control_av_model(
            model, masked_target, sigmas, prefix_steps=details["video_tokens"]
        )
        return io.NodeOutput(positive, masked_target, details["frames"], patched_model)


class MiniMaxH3FiniteSegmentFinalize(io.ComfyNode):
    """Internal finite-graph helper that removes decoded overlap."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteSegmentFinalize",
            display_name="MiniMax H3 Finite Segment Finalize (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[
                io.Latent.Input("sampled_latent"),
                io.Image.Input("images"),
                io.Int.Input("iteration", force_input=True),
                io.Int.Input("overlap_frames", default=22, min=1, max=362),
                io.Boolean.Input("trim_audio_head", default=True),
                io.Audio.Input("audio", optional=True),
            ],
            outputs=[
                io.Latent.Output(display_name="Complete Latent"),
                io.Image.Output(display_name="Deduplicated Frames"),
                io.Audio.Output(display_name="Deduplicated Audio"),
            ],
        )

    @classmethod
    def execute(
        cls, sampled_latent, images, iteration, overlap_frames,
        trim_audio_head=True, audio=None,
    ):
        trim_frames = 0 if int(iteration) <= 0 else _valid_guide_frames(int(overlap_frames))
        if images.shape[0] <= trim_frames:
            raise ValueError(f"This segment has only {images.shape[0]} frames; cannot remove a {trim_frames}-frame overlap")
        trimmed_images = images[trim_frames:].clone() if trim_frames else images
        trimmed_audio = audio
        if audio is not None and bool(trim_audio_head):
            waveform = audio.get("waveform")
            sample_rate = int(audio.get("sample_rate", 0))
            if waveform is None or sample_rate <= 0:
                raise ValueError("audio must contain waveform and a valid sample_rate")
            trim_samples = round((trim_frames / H3_FPS) * sample_rate)
            if waveform.shape[-1] <= trim_samples:
                raise ValueError("This segment's audio is too short to remove the overlap")
            trimmed_audio = dict(audio)
            trimmed_audio["waveform"] = (
                waveform[..., trim_samples:].clone() if trim_samples else waveform
            )
        return io.NodeOutput(sampled_latent, trimmed_images, trimmed_audio)


class MiniMaxH3FiniteAudioTrimTail(io.ComfyNode):
    """Internal helper that gives an incoming Soft AV segment seam ownership."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteAudioTrimTail",
            display_name="MiniMax H3 Finite Audio Tail Trim (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[
                io.Audio.Input("audio"),
                io.Int.Input("overlap_frames", default=39, min=1, max=362),
            ],
            outputs=[io.Audio.Output(display_name="Trimmed Audio")],
        )

    @classmethod
    def execute(cls, audio, overlap_frames):
        waveform = audio.get("waveform") if isinstance(audio, dict) else None
        sample_rate = int(audio.get("sample_rate", 0)) if isinstance(audio, dict) else 0
        if waveform is None or sample_rate <= 0:
            raise ValueError("audio must contain waveform and a valid sample_rate")
        trim_samples = round((_valid_guide_frames(int(overlap_frames)) / H3_FPS) * sample_rate)
        if waveform.shape[-1] <= trim_samples:
            raise ValueError("Accumulated audio is too short to replace its overlap tail")
        output = dict(audio)
        output["waveform"] = waveform[..., :-trim_samples].clone()
        return io.NodeOutput(output)


class MiniMaxH3FiniteOutputTrim(io.ComfyNode):
    """Trim auto-segment padding back to the longest source-media duration."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteOutputTrim",
            display_name="MiniMax H3 Finite Output Trim (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[
                io.Image.Input("images"),
                io.Audio.Input("audio"),
                io.Int.Input("output_frames", default=5, min=1, force_input=True),
            ],
            outputs=[
                io.Image.Output(display_name="Trimmed Frames"),
                io.Audio.Output(display_name="Trimmed Audio"),
            ],
        )

    @classmethod
    def execute(cls, images, audio, output_frames):
        frame_count = int(output_frames)
        if int(images.shape[0]) < frame_count:
            raise ValueError(
                f"Generated output has only {images.shape[0]} frames; "
                f"cannot restore a {frame_count}-frame source duration"
            )
        trimmed_images = images[:frame_count].clone()
        trimmed_audio = audio
        waveform = audio.get("waveform") if isinstance(audio, dict) else None
        sample_rate = int(audio.get("sample_rate", 0)) if isinstance(audio, dict) else 0
        if waveform is not None and sample_rate > 0:
            output_samples = round((frame_count / H3_FPS) * sample_rate)
            if waveform.shape[-1] > output_samples:
                trimmed_audio = dict(audio)
                trimmed_audio["waveform"] = waveform[..., :output_samples].clone()
        return io.NodeOutput(trimmed_images, trimmed_audio)


class MiniMaxH3FiniteSegmentSampler(io.ComfyNode):
    """Expand a finite plan into a standard acyclic sampling graph."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteSegmentSampler",
            display_name="MiniMax H3 Finite Segment Sampler",
            category="MiniMax H3/Long Video",
            description=(
                "Expand a finite plan into a standard acyclic sampling graph. Sampler and scheduler remain "
                "external; no Loop, Loop Variable, or Close Loop nodes are required."
            ),
            enable_expand=True,
            inputs=[
                io.Model.Input("model"),
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                FiniteSegmentPlan.Input("finite_plan", display_name="Finite Segment Plan"),
                io.Sampler.Input("sampler"),
                io.Sigmas.Input("sigmas"),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True),
                io.Boolean.Input("continue_audio_latent", display_name="Continue Audio Latent", default=True),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="match"),
            ],
            outputs=[
                io.Latent.Output(display_name="Last Sampled Latent"),
                io.Image.Output(display_name="Merged Frames"),
                io.Audio.Output(display_name="Merged Audio"),
                io.String.Output(display_name="Sampling Status"),
            ],
        )

    @classmethod
    def execute(
        cls, model, clip, vae, audio_vae, finite_plan, sampler, sigmas, seed,
        continue_audio_latent, ref_image_size="match",
    ):
        finite = _require_finite_plan(finite_plan)
        graph = GraphBuilder()
        previous_latent = None
        merged_images = None
        merged_audio = None
        last_sampled = None
        overlap = int(finite["overlap_frames"])
        soft_audio = bool(continue_audio_latent)
        steps = drift_control_step_count(sigmas)
        if steps < 1:
            raise ValueError(
                "Drift-Control AV requires a sigma schedule with at least one sampling step"
            )

        for index, prompt in enumerate(finite["prompts"]):
            number = index + 1
            encoder = graph.node(
                "MiniMaxH3TimelineEncoder", id=f"encode_{number}",
                clip=clip, vae=vae, audio_vae=audio_vae,
                plan=_finite_plan_for_segment(finite, number),
                prompt=prompt, ref_image_size=ref_image_size,
            )
            continuation_inputs = {
                "positive": encoder.out(0), "target_latent": encoder.out(1),
                "iteration": index, "overlap_frames": overlap,
                "continue_audio_latent": bool(continue_audio_latent),
                "model": model, "sigmas": sigmas,
            }
            if previous_latent is not None:
                continuation_inputs["previous_latent"] = previous_latent
            continuation = graph.node(
                "MiniMaxH3FiniteLatentContinuation", id=f"continue_{number}",
                **continuation_inputs,
            )
            noise = graph.node("RandomNoise", id=f"noise_{number}", noise_seed=int(seed))
            guider = graph.node(
                "BasicGuider", id=f"guider_{number}", model=continuation.out(3),
                conditioning=continuation.out(0),
            )
            sampled = graph.node(
                "SamplerCustomAdvanced", id=f"sample_{number}", noise=noise.out(0),
                guider=guider.out(0), sampler=sampler, sigmas=sigmas,
                latent_image=continuation.out(1),
            )
            images = graph.node(
                "VAEDecode", id=f"decode_video_{number}", samples=sampled.out(0), vae=vae,
            )
            audio = graph.node(
                "VAEDecodeAudio", id=f"decode_audio_{number}", samples=sampled.out(0), vae=audio_vae,
            )
            finalized = graph.node(
                "MiniMaxH3FiniteSegmentFinalize", id=f"finalize_{number}",
                sampled_latent=sampled.out(0), images=images.out(0), audio=audio.out(0),
                iteration=index, overlap_frames=overlap,
                trim_audio_head=not soft_audio,
            )
            current_images, current_audio = finalized.out(1), finalized.out(2)
            if merged_images is None:
                merged_images, merged_audio = current_images, current_audio
            else:
                image_join = graph.node(
                    "ImageBatch", id=f"join_images_{number}",
                    image1=merged_images, image2=current_images,
                )
                previous_audio_for_join = merged_audio
                if soft_audio:
                    previous_audio_for_join = graph.node(
                        "MiniMaxH3FiniteAudioTrimTail", id=f"trim_audio_tail_{number}",
                        audio=merged_audio, overlap_frames=overlap,
                    ).out(0)
                audio_join = graph.node(
                    "AudioConcat", id=f"join_audio_{number}",
                    audio1=previous_audio_for_join, audio2=current_audio, direction="after",
                )
                merged_images, merged_audio = image_join.out(0), audio_join.out(0)
            previous_latent = sampled.out(0)
            last_sampled = sampled.out(0)

        target_output_frames = int(finite.get("target_output_frames") or 0)
        if target_output_frames > 0:
            output_trim = graph.node(
                "MiniMaxH3FiniteOutputTrim", id="trim_auto_segment_output",
                images=merged_images, audio=merged_audio,
                output_frames=target_output_frames,
            )
            merged_images, merged_audio = output_trim.out(0), output_trim.out(1)

        mode_status = (
            f"Drift-Control AV {overlap}-frame mask adapted to {steps} sampling steps; overlap audio uses an 8-tick Soft AV half-cosine release"
            if continue_audio_latent
            else f"Drift-Control AV {overlap}-frame mask adapted to {steps} sampling steps; audio is independently generated"
        )
        status = (
            f"Expanded and sampled {finite['segment_count']} segments; actual overlap {overlap} frames; "
            f"all segments use seed {int(seed)}; {mode_status}; "
            f"audio latent {'continues' if continue_audio_latent else 'does not continue'}."
        )
        if target_output_frames > 0:
            trim_tail_frames = int(finite.get("trim_tail_frames") or 0)
            status += (
                f" The final {trim_tail_frames} excess tail frames and matching "
                f"audio samples are removed; output is exactly the source-media "
                f"duration ({target_output_frames} frames)."
            )
        return io.NodeOutput(
            last_sampled, merged_images, merged_audio, status, expand=graph.finalize()
        )
