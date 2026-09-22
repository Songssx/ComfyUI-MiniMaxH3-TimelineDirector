"""Plugin-owned finite MiniMax H3 long-video planning and sampling."""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

import torch
import folder_paths
from comfy.nested_tensor import NestedTensor
from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder
from comfy_extras.nodes_audio import AudioConcat

from .experimental_latent_guide import (
    _apply_linear_temporal_noise_mask,
    _valid_guide_frames,
)
from .drift_control_av import (
    drift_control_step_count,
    install_drift_control_av_model,
)
from .selflift_runtime.h3_upscaler import checkpoint_is_h3_compatible
from .minimax_h3_timeline_director import (
    TimelinePlan,
    _require_timeline_plan,
    _timeline_for_prompt_index,
    _apply_h3_guides,
    _audio_mode,
    _decode_audio,
    _safe_input_path,
    _timeline_video_audio,
)

H3_FPS = 24
FiniteSegmentPlan = io.Custom("MINIMAX_H3_FINITE_SEGMENT_PLAN")
FiniteLoopState = io.Custom("MINIMAX_H3_FINITE_LOOP_STATE")


def _selflift_settings(
    step_count: int, requested_model: str = "", requested_high_steps=None,
) -> dict:
    if step_count < 2:
        raise ValueError("Two-stage sampling requires at least two sampling steps")
    if requested_high_steps is None:
        # Old saved workflows did not contain this field. Keep them usable while
        # making four full-resolution steps the default for the common 8-step run.
        high_steps = min(4, step_count - 1)
    else:
        try:
            high_steps = int(requested_high_steps)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"High-resolution sampling steps must be an integer; got {requested_high_steps!r}"
            ) from error
        if high_steps < 1 or high_steps >= step_count:
            raise ValueError(
                "High-resolution sampling steps must be at least 1 and lower than "
                f"the Basic Scheduler step count ({step_count}); got {high_steps}"
            )
    transition = step_count - high_steps
    models = list(folder_paths.get_filename_list("latent_upscale_models"))
    if not models:
        raise ValueError(
            "Two-stage sampling requires a latent upscaler under "
            "ComfyUI/models/latent_upscale_models"
        )
    compatible_models = [name for name in models if checkpoint_is_h3_compatible(name)]
    if not compatible_models:
        raise ValueError(
            "Two-stage MiniMax H3 sampling found no compatible H3 latent upscaler under "
            "ComfyUI/models/latent_upscale_models. LTX upscalers are not compatible."
        )
    selected = str(requested_model or "").strip() or compatible_models[0]
    if selected not in models:
        raise ValueError(
            f"The selected two-stage latent upscaler is unavailable: {selected}"
        )
    if not checkpoint_is_h3_compatible(selected):
        raise ValueError(
            f"The selected latent upscaler is not compatible with MiniMax H3: {selected}. "
            f"Select {compatible_models[0]}; LTX upscalers use a different architecture."
        )
    return {
        "transition_step": transition, "lowres_scale": 0.5,
        "rho": 0.0, "w_min": 0.5, "w_max": 1.0,
        "upscaler_model": selected,
    }


@lru_cache(maxsize=8)
def _decode_locked_audio_file(
    path_text: str, modified_ns: int, file_size: int,
) -> dict | None:
    """Decode a locked soundtrack once and reuse its PCM for every segment.

    ``modified_ns`` and ``file_size`` deliberately participate in the cache key,
    so replacing an upload at the same path cannot reuse stale audio.  Decoding
    from the beginning avoids compressed-audio seek/priming errors (notably the
    repeatable 1105-sample short read produced by some MP3 files).
    """

    del modified_ns, file_size
    return _decode_audio(Path(path_text), 0.0, None)


def _locked_audio_pcm(asset: dict) -> dict:
    path = _safe_input_path(str(asset["file"]))
    stat = path.stat()
    audio = _decode_locked_audio_file(
        str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size),
    )
    if audio is None:
        raise ValueError("The locked original-audio asset could not be decoded")
    return audio


def _video_soundtrack_lock_for_plan(plan) -> dict | None:
    """Expose an enabled reference-video soundtrack as one timeline master.

    Reference-video generation must preserve the uploaded video's edited
    soundtrack in both one-stage and two-stage sampling, rather than merely
    offering it to H3 as a paired audio reference.  The synthetic asset keeps
    the existing locked-audio graph
    usable while ``_locked_audio_interval`` sources samples from the edited
    video timeline (including source trims, clip offsets, gaps, and mixes).
    """

    source = _require_timeline_plan(plan)
    timeline = source["timeline"]
    if timeline.get("videoAudioEnabled", True) is False:
        return None
    clips = [
        clip for clip in timeline.get("videoClips", [])
        if isinstance(clip, dict) and clip.get("file")
        and clip.get("hasAudio", True) is not False
        and float(clip.get("duration") or 0.0) > 0.0
    ]
    if not clips:
        return None
    identity = [
        {
            "file": str(clip["file"]),
            "start": round(float(clip.get("start") or 0.0), 6),
            "trimStart": round(float(clip.get("trimStart") or 0.0), 6),
            "duration": round(float(clip.get("duration") or 0.0), 6),
        }
        for clip in sorted(clips, key=lambda item: float(item.get("start") or 0.0))
    ]
    return {
        "lockKind": "timeline_video_audio",
        "name": "Reference video original soundtrack",
        "identity": identity,
    }


def _locked_audio_for_plan(plan, *, include_video_soundtrack: bool = True) -> dict | None:
    source = _require_timeline_plan(plan)
    assets = [
        asset for asset in source["timeline"].get("audios", [])
        if isinstance(asset, dict) and asset.get("file") and _audio_mode(asset) == "locked"
    ]
    if len(assets) > 1:
        raise ValueError("Each segment can contain at most one locked original-audio asset")
    if assets:
        # An explicitly uploaded locked soundtrack always has priority over a
        # reference video's embedded audio.
        return assets[0]
    if include_video_soundtrack:
        return _video_soundtrack_lock_for_plan(source)
    return None


def _finite_locked_audio_asset(finite: dict) -> dict | None:
    """Require one continuous locked soundtrack across a finite render."""

    plans = [
        _finite_plan_for_segment(finite, number)
        for number in range(1, int(finite["segment_count"]) + 1)
    ]
    assets = [
        _locked_audio_for_plan(plan, include_video_soundtrack=True)
        for plan in plans
    ]
    if not any(assets):
        return None
    if not all(assets):
        raise ValueError(
            "Locked original audio is enabled in only some segments; assign the same locked audio to every segment"
        )
    identity = {
        json.dumps(asset.get("identity"), sort_keys=True, ensure_ascii=False)
        if asset.get("lockKind") == "timeline_video_audio"
        else json.dumps(
            [str(asset.get("file")), round(float(asset.get("trimStart") or 0.0), 6)],
            ensure_ascii=False,
        )
        for asset in assets if asset is not None
    }
    if len(identity) != 1:
        raise ValueError(
            "A continuous locked soundtrack must use the same audio file and source-in point in every segment"
        )
    return copy.deepcopy(assets[0])


def _finite_video_audio_muted(finite: dict) -> bool:
    """Return true when a reference-video workflow explicitly disables audio.

    The video-audio switch is an output policy, not a request for H3 to invent
    a replacement soundtrack.  Explicitly uploaded locked audio still wins.
    """

    plans = [
        _finite_plan_for_segment(finite, number)
        for number in range(1, int(finite["segment_count"]) + 1)
    ]
    if any(
        _locked_audio_for_plan(plan, include_video_soundtrack=False) is not None
        for plan in plans
    ):
        return False
    has_reference_video = any(
        any(
            isinstance(clip, dict) and clip.get("file")
            for clip in _require_timeline_plan(plan)["timeline"].get("videoClips", [])
        )
        for plan in plans
    )
    if not has_reference_video:
        return False
    return all(
        _require_timeline_plan(plan)["timeline"].get("videoAudioEnabled", True) is False
        for plan in plans
    )


def _locked_audio_interval(plan, *, output_frames: int | None = None) -> dict:
    source = _require_timeline_plan(plan)
    asset = _locked_audio_for_plan(source)
    if asset is None:
        raise ValueError("This material plan has no locked original-audio asset")
    selection = source["timeline"].get("selection") or {}
    timeline_start = max(0.0, float(selection.get("start") or 0.0))
    frame_count = int(output_frames or source.get("length") or 0)
    if frame_count < 1:
        raise ValueError("The locked-audio interval has no target frames")
    duration = frame_count / H3_FPS
    if asset.get("lockKind") == "timeline_video_audio":
        # The mixed waveform is already laid out in timeline coordinates.
        source_start = timeline_start
        audio = _timeline_video_audio(source["timeline"])
    else:
        source_start = max(0.0, float(asset.get("trimStart") or 0.0)) + timeline_start
        audio = _locked_audio_pcm(asset)
    expected = round(duration * int(audio["sample_rate"]))
    source_sample = round(source_start * int(audio["sample_rate"]))
    waveform = audio["waveform"]
    source_sample = min(max(0, source_sample), int(waveform.shape[-1]))
    waveform = waveform[..., source_sample:source_sample + expected]
    if waveform.shape[-1] < expected:
        # H3 needs a legal AV latent duration even when the soundtrack ends in
        # the middle of a segment.  Silence is internal padding only: existing
        # source samples remain bit-for-bit unchanged, while the final output
        # follows the user's timeline duration without requiring frame-perfect
        # audio metadata.
        waveform = torch.nn.functional.pad(
            waveform, (0, expected - int(waveform.shape[-1])),
        )
    result = dict(audio)
    result["waveform"] = waveform[..., :expected].clone()
    return result


def _silent_audio_interval(plan, *, output_frames: int | None = None) -> dict:
    source = _require_timeline_plan(plan)
    frame_count = int(output_frames or source.get("length") or 0)
    if frame_count < 1:
        raise ValueError("The silent-audio interval has no target frames")
    sample_rate = 44100
    sample_count = max(1, round((frame_count / H3_FPS) * sample_rate))
    return {
        "waveform": torch.zeros((1, 1, sample_count), dtype=torch.float32),
        "sample_rate": sample_rate,
    }


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


def _prepare_timeline_segments(source):
    """Compile the planner's frame windows without changing their visible geometry."""
    source = _require_timeline_plan(source)
    if source.get("prompt_index") is not None:
        raise ValueError("Disconnect Prompt Index when generating all timeline segments")
    config = source["timeline"].get("segmentConfig", {})
    segments = config.get("segments", [])
    count = int(config.get("count", 0))
    global_prompt = str(source["timeline"].get("globalPrompt") or "").strip()

    # The Material Planner is also the single-segment text-to-video planner.
    # With no windows, its current GEN selection becomes one finite segment;
    # the encoder created inside Finite Segment Sampling already knows how to
    # create an empty H3 AV latent when the plan contains no reference media.
    if count == 0:
        if not global_prompt:
            raise ValueError("Enter a Global Prompt in the Material Planner")
        length = int(source.get("length") or 0)
        if length < 5 or (length - 5) % 17 or length > 3592:
            raise ValueError("The Material Planner generation duration must resolve to 5 + 17*n frames")
        plan = copy.deepcopy(source)
        plan["timeline"]["segmentConfig"] = {"count": 0, "segments": []}
        return {
            "type": "minimax_h3_finite_segment_plan", "version": 4,
            "mode": "single_segment", "source_plan": source,
            "segment_count": 1, "segment_plans": [plan],
            "prompts": [global_prompt], "overlap_frames": 0,
            "segment_overlaps": [0], "segment_lengths": [length],
            "target_output_frames": length,
            "second_pass": bool(source["timeline"].get("secondPass")),
            "second_pass_model": str(source["timeline"].get("secondPassModel") or ""),
            "second_pass_high_steps": source["timeline"].get("secondPassHighSteps"),
        }

    if config.get("mode") != "timeline" or not 1 <= count <= 64:
        raise ValueError("Click Update segments in the Material Planner before generating")
    if len(segments) != count:
        raise ValueError("The segment count does not match the timeline windows")
    local_prompts = [str(segment.get("prompt") or "").strip() for segment in segments]
    if any(local_prompts):
        if not all(local_prompts):
            missing = ", ".join(str(index + 1) for index, prompt in enumerate(local_prompts) if not prompt)
            raise ValueError(
                "Segment prompt mode is active because at least one segment has a prompt; "
                f"enter prompts for every segment (missing: {missing})"
            )
        resolved_prompts = local_prompts
    else:
        if not global_prompt:
            raise ValueError("Enter a Global Prompt in the Material Planner, or enter a prompt for every segment")
        resolved_prompts = [global_prompt] * len(segments)

    plans, prompts, overlaps, lengths = [], [], [], []
    previous_start = previous_end = 0
    for index, segment in enumerate(segments):
        start, end = segment.get("startFrame"), segment.get("endFrame")
        if type(start) is not int or type(end) is not int:
            raise ValueError(f"Segment {index + 1} requires integer frame boundaries")
        length = end - start
        if start < 0 or length < 5 or (length - 5) % 17 or length > 3592:
            raise ValueError(f"Segment {index + 1} length must be 5 + 17*n frames (up to 150 seconds)")
        overlap = previous_end - start if index else 0
        if (not index and start != 0) or (index and (
            start <= previous_start or end <= previous_end or overlap < 0
            or overlap >= min(length, lengths[-1])
            or (overlap and _valid_guide_frames(overlap) != overlap)
        )):
            raise ValueError(f"Segment {index + 1} must advance in time without gaps and use an H3-aligned overlap")
        plan = _plan_for_segment(source, index + 1)
        plan["timeline"]["selection"] = {"start": start / H3_FPS, "duration": length / H3_FPS}
        plan["generation_seconds"], plan["length"] = length / H3_FPS, length
        plan["timeline"]["segmentConfig"] = {"count": 0, "segments": []}
        # Selected audio is local to this segment (short timbre references remain reusable).
        plans.append(plan)
        prompts.append(resolved_prompts[index])
        overlaps.append(overlap)
        lengths.append(length)
        previous_start, previous_end = start, end
    return {
        "type": "minimax_h3_finite_segment_plan", "version": 3,
        "mode": "timeline_segments", "source_plan": source,
        "segment_count": len(plans), "segment_plans": plans, "prompts": prompts,
        "overlap_frames": 0, "segment_overlaps": overlaps,
        "segment_lengths": lengths, "target_output_frames": previous_end,
        "second_pass": bool(source["timeline"].get("secondPass")),
        "second_pass_model": str(source["timeline"].get("secondPassModel") or ""),
        "second_pass_high_steps": source["timeline"].get("secondPassHighSteps"),
    }


def _require_finite_plan(value):
    if isinstance(value, dict) and value.get("type") == "MINIMAX_H3_TIMELINE_PLAN":
        value = _prepare_timeline_segments(value)
    if not isinstance(value, dict) or value.get("type") != "minimax_h3_finite_segment_plan":
        raise ValueError("finite_plan must come from MiniMax H3 Material Planner or a legacy finite segment plan")
    count = int(value.get("segment_count") or 0)
    prompts = value.get("prompts")
    if count < 1 or not isinstance(prompts, list) or len(prompts) != count:
        raise ValueError("The finite segment plan is incomplete; update the segment plan and run it again")
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
            is_deprecated=True,
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
                io.Int.Input("overlap_frames", default=22, min=0, max=3592),
                io.Boolean.Input("continue_audio_latent", default=True),
                io.Model.Input("model"),
                io.Sigmas.Input("sigmas"),
                io.Latent.Input("previous_latent", optional=True),
                io.Image.Input("previous_images", optional=True),
                io.Vae.Input("vae", optional=True),
                io.Vae.Input("audio_vae", optional=True),
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
        previous_images=None, vae=None, audio_vae=None,
    ):
        if int(overlap_frames) == 0:
            # Touching windows are independent: no video or audio continuation.
            return io.NodeOutput(positive, target_latent, 0, model)
        if int(iteration) > 0 and int(overlap_frames) == 1:
            if previous_images is None or vae is None or audio_vae is None:
                raise ValueError("Touching segments require the preceding final image and VAEs")
            positive = _apply_h3_guides(positive, target_latent, vae, audio_vae, [{
                "image": previous_images[-1:].clone(), "audio": None, "frame_idx": 0,
            }])
            return io.NodeOutput(positive, target_latent, int(overlap_frames), model)
        actual_overlap = _valid_guide_frames(int(overlap_frames))
        if int(iteration) <= 0:
            return io.NodeOutput(positive, target_latent, 0 if int(overlap_frames) == 0 else actual_overlap, model)
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
        # SelfLift keeps its native pre-lift low-resolution prediction beside
        # the final high-resolution result. Carry that low-grid state into the
        # next segment so Drift-Control does not reconstruct it by shrinking
        # the preceding final high-resolution latent again.
        previous_low_carry = previous_latent.get("selflift_low_resolution_carry")
        if previous_low_carry is not None:
            masked_target = dict(masked_target)
            masked_target["selflift_previous_low_resolution_carry"] = previous_low_carry
        patched_model = install_drift_control_av_model(
            model, masked_target, sigmas, prefix_steps=details["video_tokens"]
        )
        return io.NodeOutput(positive, masked_target, details["frames"], patched_model)


class MiniMaxH3LockedAudioSlice(io.ComfyNode):
    """Internal helper that reads the exact soundtrack interval for one GEN window."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LockedAudioSlice",
            display_name="MiniMax H3 Locked Audio Slice (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[TimelinePlan.Input("plan", display_name="Material Plan")],
            outputs=[io.Audio.Output(display_name="Locked Audio")],
        )

    @classmethod
    def execute(cls, plan):
        return io.NodeOutput(_locked_audio_interval(plan))


class MiniMaxH3SilentAudioSlice(io.ComfyNode):
    """Internal helper that fixes one reference-video segment to silence."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3SilentAudioSlice",
            display_name="MiniMax H3 Silent Audio Slice (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[TimelinePlan.Input("plan", display_name="Material Plan")],
            outputs=[io.Audio.Output(display_name="Silent Audio")],
        )

    @classmethod
    def execute(cls, plan):
        return io.NodeOutput(_silent_audio_interval(plan))


class MiniMaxH3LockAudioLatent(io.ComfyNode):
    """Replace the H3 target audio stream and exclude it from denoising."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LockAudioLatent",
            display_name="MiniMax H3 Lock Audio Latent (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[
                io.Latent.Input("target_latent"),
                io.Latent.Input("audio_latent"),
            ],
            outputs=[io.Latent.Output(display_name="Locked AV Latent")],
        )

    @classmethod
    def execute(cls, target_latent, audio_latent):
        target_samples = target_latent.get("samples") if isinstance(target_latent, dict) else None
        source_audio = audio_latent.get("samples") if isinstance(audio_latent, dict) else None
        if target_samples is None or not getattr(target_samples, "is_nested", False):
            raise ValueError("Locked audio requires a nested MiniMax H3 AV latent")
        streams = list(target_samples.unbind())
        if len(streams) != 2 or source_audio is None or getattr(source_audio, "is_nested", False):
            raise ValueError("Locked audio requires one encoded audio latent")
        video, target_audio = streams
        source_audio = source_audio.to(device=target_audio.device, dtype=target_audio.dtype)
        if source_audio.ndim != target_audio.ndim or tuple(source_audio.shape[:-1]) != tuple(target_audio.shape[:-1]):
            raise ValueError(
                f"Encoded locked audio {tuple(source_audio.shape)} is incompatible with H3 target audio {tuple(target_audio.shape)}"
            )
        if source_audio.shape[-1] < target_audio.shape[-1]:
            source_audio = torch.nn.functional.pad(
                source_audio, (0, int(target_audio.shape[-1] - source_audio.shape[-1]))
            )
        locked_audio = source_audio[..., :target_audio.shape[-1]].clone()

        existing_mask = target_latent.get("noise_mask")
        if existing_mask is not None and getattr(existing_mask, "is_nested", False):
            video_mask = existing_mask.unbind()[0]
        elif torch.is_tensor(existing_mask):
            video_mask = existing_mask
        else:
            video_mask = torch.ones(
                (video.shape[0], 1, video.shape[2], 1, 1),
                dtype=torch.float32, device=video.device,
            )
        audio_mask = torch.zeros(
            (target_audio.shape[0], 1, 1, target_audio.shape[-1]),
            dtype=torch.float32, device=target_audio.device,
        )
        output = dict(target_latent)
        output["samples"] = NestedTensor((video, locked_audio))
        output["noise_mask"] = NestedTensor((video_mask, audio_mask))
        return io.NodeOutput(output)


class MiniMaxH3LockedAudioMaster(io.ComfyNode):
    """Decode the continuous original waveform once for the final video output."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LockedAudioMaster",
            display_name="MiniMax H3 Locked Audio Master (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[FiniteSegmentPlan.Input("finite_plan", display_name="Finite Segment Plan")],
            outputs=[io.Audio.Output(display_name="Original Audio")],
        )

    @classmethod
    def execute(cls, finite_plan):
        finite = _require_finite_plan(finite_plan)
        asset = _finite_locked_audio_asset(finite)
        if asset is None:
            raise ValueError("The finite plan has no locked original soundtrack")
        first = _finite_plan_for_segment(finite, 1)
        target_frames = int(finite.get("target_output_frames") or 0)
        if target_frames < 1:
            target_frames = sum(int(value) for value in finite.get("segment_lengths", []))
            target_frames -= sum(int(value) for value in finite.get("segment_overlaps", [])[1:])
        if target_frames < 1:
            target_frames = int(first.get("length") or 0)
        master_plan = copy.deepcopy(first)
        if asset.get("lockKind") != "timeline_video_audio":
            master_plan["timeline"]["audios"] = [asset]
        return io.NodeOutput(_locked_audio_interval(master_plan, output_frames=target_frames))


class MiniMaxH3SilentAudioMaster(io.ComfyNode):
    """Return a duration-exact silent master when video audio is disabled."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3SilentAudioMaster",
            display_name="MiniMax H3 Silent Audio Master (Internal)",
            category="MiniMax H3/Internal",
            is_dev_only=True,
            inputs=[FiniteSegmentPlan.Input("finite_plan", display_name="Finite Segment Plan")],
            outputs=[io.Audio.Output(display_name="Silent Audio")],
        )

    @classmethod
    def execute(cls, finite_plan):
        finite = _require_finite_plan(finite_plan)
        first = _finite_plan_for_segment(finite, 1)
        target_frames = int(finite.get("target_output_frames") or 0)
        if target_frames < 1:
            target_frames = sum(int(value) for value in finite.get("segment_lengths", []))
            target_frames -= sum(int(value) for value in finite.get("segment_overlaps", [])[1:])
        if target_frames < 1:
            target_frames = int(first.get("length") or 0)
        return io.NodeOutput(_silent_audio_interval(first, output_frames=target_frames))


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
                io.Int.Input("overlap_frames", default=22, min=0, max=3592),
                io.Boolean.Input("trim_audio_head", default=True),
                io.Audio.Input("audio", optional=True),
                io.Image.Input("accumulated_images", optional=True),
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
        trim_audio_head=True, audio=None, accumulated_images=None,
    ):
        trim_frames = 0 if int(iteration) <= 0 or int(overlap_frames) == 0 else _valid_guide_frames(int(overlap_frames))
        if images.shape[0] <= trim_frames:
            raise ValueError(f"This segment has only {images.shape[0]} frames; cannot remove a {trim_frames}-frame overlap")
        trimmed_images = images[trim_frames:].clone() if trim_frames else images
        if accumulated_images is not None:
            # The preceding segment owns the visual overlap. Preserve its
            # decoded tail and discard the duplicate opening interval from the
            # incoming segment before joining the two timelines.
            trimmed_images = torch.cat((accumulated_images, trimmed_images), dim=0)
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
                io.Int.Input("overlap_frames", default=39, min=1, max=3592),
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


class MiniMaxH3FiniteLoopInitialize(io.ComfyNode):
    """Create the carried value used by ComfyUI's native Start/End Loop nodes."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteLoopInitialize",
            display_name="MiniMax H3 Initialize Segment Loop",
            category="MiniMax H3/Long Video/Loop",
            description=(
                "Initialize native ComfyUI Loop state for a finite H3 segment plan. Connect this to "
                "Start Loop's initial_iteration_value."
            ),
            inputs=[FiniteSegmentPlan.Input("finite_plan", display_name="Finite Segment Plan")],
            outputs=[
                FiniteLoopState.Output(display_name="Initial Loop State"),
                io.Int.Output(display_name="Segment Count"),
            ],
        )

    @classmethod
    def execute(cls, finite_plan):
        finite = _require_finite_plan(finite_plan)
        state = {
            "finite_plan": finite,
            "next_iteration": 0,
            "previous_latent": None,
            "previous_images": None,
            "merged_images": None,
            "merged_audio": None,
        }
        return io.NodeOutput(state, int(finite["segment_count"]))


class MiniMaxH3FiniteLoopSegment(io.ComfyNode):
    """Select one material plan and prompt from a native Loop iteration index."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteLoopSegment",
            display_name="MiniMax H3 Select Loop Segment",
            category="MiniMax H3/Long Video/Loop",
            description=(
                "Resolve the current per-segment material plan, prompt, and overlap. Connect a native "
                "Start Loop iteration_index, then feed the plan and prompt to MiniMax H3 Plan Encoder."
            ),
            inputs=[
                FiniteSegmentPlan.Input("finite_plan", display_name="Finite Segment Plan"),
                io.Int.Input("iteration_index", force_input=True),
            ],
            outputs=[
                TimelinePlan.Output(display_name="Segment Material Plan"),
                io.String.Output(display_name="Segment Prompt"),
                io.Int.Output(display_name="Overlap Frames"),
                io.Boolean.Output(display_name="Use Two-Stage Sampling"),
                io.String.Output(display_name="Two-Stage Model"),
                io.Int.Output(display_name="High-Resolution Steps"),
            ],
        )

    @classmethod
    def execute(cls, finite_plan, iteration_index):
        finite = _require_finite_plan(finite_plan)
        index = int(iteration_index)
        if index < 0 or index >= int(finite["segment_count"]):
            raise ValueError(
                f"Loop iteration {index} is outside the {finite['segment_count']}-segment plan"
            )
        overlap = int(finite.get("segment_overlaps", [finite["overlap_frames"]] * finite["segment_count"])[index])
        return io.NodeOutput(
            _finite_plan_for_segment(finite, index + 1),
            finite["prompts"][index],
            overlap,
            bool(finite.get("second_pass")),
            str(finite.get("second_pass_model") or ""),
            int(finite.get("second_pass_high_steps") or 1),
        )


class MiniMaxH3FiniteLoopPrepare(io.ComfyNode):
    """Apply previous-segment continuation and fixed-audio policy before sampling."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteLoopPrepare",
            display_name="MiniMax H3 Prepare Loop Segment",
            category="MiniMax H3/Long Video/Loop",
            description=(
                "Prepare one encoded H3 segment for sampling. It carries the preceding latent tail, applies "
                "Drift-Control, and locks original or muted video audio when requested by the material plan."
            ),
            enable_expand=True,
            inputs=[
                FiniteSegmentPlan.Input("finite_plan", display_name="Finite Segment Plan"),
                FiniteLoopState.Input("loop_state", display_name="Current Loop State"),
                TimelinePlan.Input("segment_plan", display_name="Segment Material Plan"),
                io.Conditioning.Input("positive"),
                io.Latent.Input("target_latent"),
                io.Model.Input("model"),
                io.Sigmas.Input("sigmas"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.Int.Input("iteration_index", force_input=True),
                io.Boolean.Input("continue_audio_latent", display_name="Continue Audio Latent", default=True),
            ],
            outputs=[
                io.Conditioning.Output(display_name="Positive"),
                io.Latent.Output(display_name="Sampling Latent"),
                io.Model.Output(display_name="Sampling Model"),
                io.Int.Output(display_name="Actual Overlap Frames"),
            ],
        )

    @classmethod
    def execute(
        cls, finite_plan, loop_state, segment_plan, positive, target_latent,
        model, sigmas, vae, audio_vae, iteration_index, continue_audio_latent,
    ):
        finite = _require_finite_plan(finite_plan)
        index = int(iteration_index)
        if not isinstance(loop_state, dict) or int(loop_state.get("next_iteration", -1)) != index:
            raise ValueError("The native Loop carried state does not match the current segment iteration")
        expected_plan = _finite_plan_for_segment(finite, index + 1)
        if int(segment_plan.get("length") or 0) != int(expected_plan.get("length") or 0):
            raise ValueError("The selected segment plan does not match this Loop iteration")

        overlap = int(finite.get("segment_overlaps", [finite["overlap_frames"]] * finite["segment_count"])[index])
        locked_audio = _finite_locked_audio_asset(finite)
        muted_video_audio = _finite_video_audio_muted(finite)
        fixed_audio = locked_audio is not None or muted_video_audio
        graph = GraphBuilder()
        continuation_inputs = {
            "positive": positive,
            "target_latent": target_latent,
            "iteration": index,
            "overlap_frames": overlap,
            "continue_audio_latent": bool(continue_audio_latent) and not fixed_audio,
            "model": model,
            "sigmas": sigmas,
        }
        previous_latent = loop_state.get("previous_latent")
        if previous_latent is not None and overlap > 0:
            continuation_inputs["previous_latent"] = previous_latent
            if overlap == 1:
                continuation_inputs.update(
                    previous_images=loop_state.get("previous_images"),
                    vae=vae,
                    audio_vae=audio_vae,
                )
        continuation = graph.node(
            "MiniMaxH3FiniteLatentContinuation",
            id="loop_segment_continuation",
            **continuation_inputs,
        )
        sampling_latent = continuation.out(1)
        if fixed_audio:
            source_audio = graph.node(
                "MiniMaxH3LockedAudioSlice" if locked_audio is not None else "MiniMaxH3SilentAudioSlice",
                id="loop_segment_audio",
                plan=segment_plan,
            )
            encoded_audio = graph.node(
                "VAEEncodeAudio",
                id="loop_segment_audio_encode",
                audio=source_audio.out(0),
                vae=audio_vae,
            )
            sampling_latent = graph.node(
                "MiniMaxH3LockAudioLatent",
                id="loop_segment_audio_lock",
                target_latent=sampling_latent,
                audio_latent=encoded_audio.out(0),
            ).out(0)
        return io.NodeOutput(
            continuation.out(0), sampling_latent, continuation.out(3), continuation.out(2),
            expand=graph.finalize(),
        )


class MiniMaxH3FiniteLoopAccumulate(io.ComfyNode):
    """Store the sampled tail and merge one decoded segment into carried Loop state."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteLoopAccumulate",
            display_name="MiniMax H3 Accumulate Loop Segment",
            category="MiniMax H3/Long Video/Loop",
            description=(
                "Remove the duplicated opening overlap, append decoded frames and audio, and return the state "
                "that must connect to End Loop's next_iteration_value."
            ),
            inputs=[
                FiniteSegmentPlan.Input("finite_plan", display_name="Finite Segment Plan"),
                FiniteLoopState.Input("loop_state", display_name="Current Loop State"),
                io.Latent.Input("sampled_latent"),
                io.Image.Input("images"),
                io.Audio.Input("audio"),
                io.Int.Input("iteration_index", force_input=True),
                io.Boolean.Input("continue_audio_latent", display_name="Continue Audio Latent", default=True),
            ],
            outputs=[
                FiniteLoopState.Output(display_name="Next Loop State"),
                io.Image.Output(display_name="Merged Frames"),
                io.Audio.Output(display_name="Merged Audio"),
            ],
        )

    @classmethod
    def execute(
        cls, finite_plan, loop_state, sampled_latent, images, audio,
        iteration_index, continue_audio_latent,
    ):
        finite = _require_finite_plan(finite_plan)
        index = int(iteration_index)
        if not isinstance(loop_state, dict) or int(loop_state.get("next_iteration", -1)) != index:
            raise ValueError("The native Loop carried state does not match the current segment iteration")
        overlap = int(finite.get("segment_overlaps", [finite["overlap_frames"]] * finite["segment_count"])[index])
        trim_frames = 0 if index <= 0 or overlap == 0 else _valid_guide_frames(overlap)
        if images.shape[0] <= trim_frames:
            raise ValueError(f"This segment has only {images.shape[0]} frames; cannot remove a {trim_frames}-frame overlap")
        current_images = images[trim_frames:].clone() if trim_frames else images
        merged_images = loop_state.get("merged_images")
        if merged_images is not None:
            merged_images = torch.cat((merged_images, current_images), dim=0)
        else:
            merged_images = current_images

        locked_audio = _finite_locked_audio_asset(finite)
        muted_video_audio = _finite_video_audio_muted(finite)
        soft_audio = bool(continue_audio_latent) and locked_audio is None and not muted_video_audio
        current_audio = audio
        if not soft_audio and trim_frames:
            waveform = audio.get("waveform")
            sample_rate = int(audio.get("sample_rate", 0))
            if waveform is None or sample_rate <= 0:
                raise ValueError("audio must contain waveform and a valid sample_rate")
            trim_samples = round((trim_frames / H3_FPS) * sample_rate)
            if waveform.shape[-1] <= trim_samples:
                raise ValueError("This segment's audio is too short to remove the overlap")
            current_audio = dict(audio)
            current_audio["waveform"] = waveform[..., trim_samples:].clone()

        merged_audio = loop_state.get("merged_audio")
        if merged_audio is not None:
            if soft_audio and overlap > 0:
                merged_audio = MiniMaxH3FiniteAudioTrimTail.execute(
                    merged_audio, overlap,
                ).result[0]
            merged_audio = AudioConcat.execute(
                audio1=merged_audio, audio2=current_audio, direction="after",
            ).result[0]
        else:
            merged_audio = current_audio

        state = {
            "finite_plan": finite,
            "next_iteration": index + 1,
            "previous_latent": sampled_latent,
            "previous_images": images,
            "merged_images": merged_images,
            "merged_audio": merged_audio,
        }
        return io.NodeOutput(state, merged_images, merged_audio)


class MiniMaxH3FiniteLoopOutput(io.ComfyNode):
    """Resolve the final carried state after native End Loop completes."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteLoopOutput",
            display_name="MiniMax H3 Finish Segment Loop",
            category="MiniMax H3/Long Video/Loop",
            description=(
                "Convert End Loop's final carried state into the last latent and merged video/audio, including "
                "duration trimming and exact locked or muted soundtrack replacement."
            ),
            inputs=[FiniteLoopState.Input("loop_state", display_name="Final Loop State")],
            outputs=[
                io.Latent.Output(display_name="Last Sampled Latent"),
                io.Image.Output(display_name="Merged Frames"),
                io.Audio.Output(display_name="Merged Audio"),
                io.String.Output(display_name="Loop Status"),
            ],
        )

    @classmethod
    def execute(cls, loop_state):
        if not isinstance(loop_state, dict):
            raise ValueError("loop_state must come from MiniMax H3 Accumulate Loop Segment")
        finite = _require_finite_plan(loop_state.get("finite_plan"))
        completed = int(loop_state.get("next_iteration", 0))
        if completed != int(finite["segment_count"]):
            raise ValueError(
                f"The native Loop completed {completed} of {finite['segment_count']} segments"
            )
        images = loop_state.get("merged_images")
        audio = loop_state.get("merged_audio")
        last_latent = loop_state.get("previous_latent")
        if images is None or audio is None or last_latent is None:
            raise ValueError("The native Loop did not produce a complete sampled segment state")

        target_output_frames = int(finite.get("target_output_frames") or 0)
        if target_output_frames > 0:
            images, audio = MiniMaxH3FiniteOutputTrim.execute(
                images, audio, target_output_frames,
            ).result
        locked_audio = _finite_locked_audio_asset(finite)
        if locked_audio is not None:
            first = _finite_plan_for_segment(finite, 1)
            master_plan = copy.deepcopy(first)
            if locked_audio.get("lockKind") != "timeline_video_audio":
                master_plan["timeline"]["audios"] = [locked_audio]
            output_frames = target_output_frames or int(images.shape[0])
            audio = _locked_audio_interval(master_plan, output_frames=output_frames)
        elif _finite_video_audio_muted(finite):
            audio = _silent_audio_interval(
                _finite_plan_for_segment(finite, 1),
                output_frames=target_output_frames or int(images.shape[0]),
            )
        status = (
            f"Native ComfyUI Loop completed {completed} H3 segments; "
            f"merged output contains {int(images.shape[0])} frames."
        )
        return io.NodeOutput(last_latent, images, audio, status)


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
        previous_images = None
        merged_images = None
        merged_audio = None
        last_sampled = None
        overlap = int(finite["overlap_frames"])
        locked_audio = _finite_locked_audio_asset(finite)
        muted_video_audio = _finite_video_audio_muted(finite)
        fixed_audio = locked_audio is not None or muted_video_audio
        soft_audio = bool(continue_audio_latent) and not fixed_audio
        steps = drift_control_step_count(sigmas)
        if steps < 1:
            raise ValueError(
                "Drift-Control AV requires a sigma schedule with at least one sampling step"
            )
        second_pass = bool(finite.get("second_pass"))
        selflift_settings = (
            _selflift_settings(
                steps,
                finite.get("second_pass_model", ""),
                finite.get("second_pass_high_steps"),
            )
            if second_pass else None
        )

        for index, prompt in enumerate(finite["prompts"]):
            number = index + 1
            overlap = int(finite.get("segment_overlaps", [overlap] * finite["segment_count"])[index])
            segment_plan = _finite_plan_for_segment(finite, number)
            encoder = graph.node(
                "MiniMaxH3TimelineEncoder", id=f"encode_{number}",
                clip=clip, vae=vae, audio_vae=audio_vae,
                plan=segment_plan,
                prompt=prompt, ref_image_size=ref_image_size,
            )
            continuation_inputs = {
                "positive": encoder.out(0), "target_latent": encoder.out(1),
                "iteration": index, "overlap_frames": overlap,
                "continue_audio_latent": bool(continue_audio_latent) and not fixed_audio,
                "model": model, "sigmas": sigmas,
            }
            if previous_latent is not None and overlap > 0:
                continuation_inputs["previous_latent"] = previous_latent
                if overlap == 1:
                    continuation_inputs.update(previous_images=previous_images, vae=vae, audio_vae=audio_vae)
            continuation = graph.node(
                "MiniMaxH3FiniteLatentContinuation", id=f"continue_{number}",
                **continuation_inputs,
            )
            sampling_latent = continuation.out(1)
            if fixed_audio:
                source_audio = graph.node(
                    "MiniMaxH3LockedAudioSlice" if locked_audio is not None else "MiniMaxH3SilentAudioSlice",
                    id=(f"locked_audio_slice_{number}" if locked_audio is not None else f"silent_audio_slice_{number}"),
                    plan=segment_plan,
                )
                encoded_audio = graph.node(
                    "VAEEncodeAudio", id=f"fixed_audio_encode_{number}",
                    audio=source_audio.out(0), vae=audio_vae,
                )
                sampling_latent = graph.node(
                    "MiniMaxH3LockAudioLatent", id=f"fixed_audio_latent_{number}",
                    target_latent=sampling_latent, audio_latent=encoded_audio.out(0),
                ).out(0)
            if second_pass:
                sampled = graph.node(
                    "MiniMaxH3TimelineSelfLiftSampler", id=f"sample_{number}",
                    model=continuation.out(3), positive=continuation.out(0),
                    negative=continuation.out(0), vae=vae,
                    latent_image=sampling_latent, sampler=sampler, sigmas=sigmas,
                    seed=int(seed), cfg=1.0, **selflift_settings,
                )
            else:
                noise = graph.node("RandomNoise", id=f"noise_{number}", noise_seed=int(seed))
                guider = graph.node(
                    "BasicGuider", id=f"guider_{number}", model=continuation.out(3),
                    conditioning=continuation.out(0),
                )
                sampled = graph.node(
                    "SamplerCustomAdvanced", id=f"sample_{number}", noise=noise.out(0),
                    guider=guider.out(0), sampler=sampler, sigmas=sigmas,
                    latent_image=sampling_latent,
                )
            images = graph.node(
                "VAEDecode", id=f"decode_video_{number}", samples=sampled.out(0), vae=vae,
            )
            audio = graph.node(
                "VAEDecodeAudio", id=f"decode_audio_{number}", samples=sampled.out(0), vae=audio_vae,
            )
            finalize_inputs = {}
            if merged_images is not None:
                finalize_inputs["accumulated_images"] = merged_images
            finalized = graph.node(
                "MiniMaxH3FiniteSegmentFinalize", id=f"finalize_{number}",
                sampled_latent=sampled.out(0), images=images.out(0), audio=audio.out(0),
                iteration=index, overlap_frames=overlap,
                trim_audio_head=not soft_audio,
                **finalize_inputs,
            )
            current_images, current_audio = finalized.out(1), finalized.out(2)
            if merged_images is None:
                merged_images, merged_audio = current_images, current_audio
            else:
                previous_audio_for_join = merged_audio
                if soft_audio and overlap > 0:
                    previous_audio_for_join = graph.node(
                        "MiniMaxH3FiniteAudioTrimTail", id=f"trim_audio_tail_{number}",
                        audio=merged_audio, overlap_frames=overlap,
                    ).out(0)
                audio_join = graph.node(
                    "AudioConcat", id=f"join_audio_{number}",
                    audio1=previous_audio_for_join, audio2=current_audio, direction="after",
                )
                merged_images, merged_audio = current_images, audio_join.out(0)
            previous_latent = sampled.out(0)
            previous_images = images.out(0)
            last_sampled = sampled.out(0)

        target_output_frames = int(finite.get("target_output_frames") or 0)
        if target_output_frames > 0:
            output_trim = graph.node(
                "MiniMaxH3FiniteOutputTrim", id="trim_auto_segment_output",
                images=merged_images, audio=merged_audio,
                output_frames=target_output_frames,
            )
            merged_images, merged_audio = output_trim.out(0), output_trim.out(1)

        if locked_audio is not None:
            merged_audio = graph.node(
                "MiniMaxH3LockedAudioMaster", id="locked_audio_master",
                finite_plan=finite,
            ).out(0)
        elif muted_video_audio:
            merged_audio = graph.node(
                "MiniMaxH3SilentAudioMaster", id="silent_audio_master",
                finite_plan=finite,
            ).out(0)

        locked_video_soundtrack = bool(
            locked_audio is not None
            and locked_audio.get("lockKind") == "timeline_video_audio"
        )
        mode_status = (
            "the reference-video soundtrack is encoded into every segment with a zero audio denoise mask, and the final output uses its exact edited timeline waveform"
            if locked_video_soundtrack else
            "the source soundtrack is encoded into every segment with a zero audio denoise mask, and the final output uses the original continuous waveform"
            if locked_audio is not None else
            "reference-video audio is disabled, so every segment uses a zero-denoise silent audio latent and the final output is silent"
            if muted_video_audio else
            f"Drift-Control AV {overlap}-frame mask adapted to {steps} sampling steps; overlap audio uses an 8-tick Soft AV half-cosine release"
            if continue_audio_latent
            else f"Drift-Control AV {overlap}-frame mask adapted to {steps} sampling steps; audio is independently generated"
        )
        status = (
            f"Expanded and sampled {finite['segment_count']} segments; actual overlap {overlap} frames; "
            f"all segments use seed {int(seed)}; {mode_status}; "
            f"audio latent {'is locked to the source' if locked_audio is not None else ('is fixed to silence' if muted_video_audio else ('continues' if continue_audio_latent else 'does not continue'))}."
        )
        if finite.get("mode") == "timeline_segments":
            status = (
                f"Sampled {finite['segment_count']} timeline windows; lengths={finite['segment_lengths']}; "
                f"seam overlaps={finite['segment_overlaps']}. Zero-overlap seams are generated "
                "independently without previous-segment guidance or frame removal."
            )
            if locked_audio is not None:
                status += (
                    " The reference-video soundtrack" if locked_video_soundtrack
                    else " The uploaded locked soundtrack"
                )
                status += (
                    " is encoded into every segment with a zero audio denoise mask; "
                    "final audio is the original continuous waveform."
                )
            elif muted_video_audio:
                status += (
                    " Video source audio is disabled, so every segment uses a "
                    "zero-denoise silent audio latent and final output is silent."
                )
        if second_pass:
            status += (
                f" Two-stage sampling ran on every segment: {selflift_settings['transition_step']} "
                f"low-resolution step(s), {steps - selflift_settings['transition_step']} "
                "full-resolution step(s); segment 2+ reuses both the preceding native "
                "low-resolution tail for the low stage and the preceding final "
                "high-resolution tail as the masked high-stage opening anchor."
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
