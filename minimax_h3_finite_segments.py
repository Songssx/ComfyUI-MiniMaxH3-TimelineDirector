"""Plugin-owned finite MiniMax H3 long-video planning and sampling."""

from __future__ import annotations

import copy
import json
import re

import node_helpers
from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder

from .experimental_latent_guide import (
    _apply_linear_temporal_noise_mask,
    _build_direct_latent_keyframe,
    _valid_guide_frames,
)
from .minimax_h3_timeline_director import (
    TimelinePlan,
    _require_timeline_plan,
    _timeline_for_prompt_index,
)

H3_FPS = 24
FiniteSegmentPlan = io.Custom("MINIMAX_H3_FINITE_SEGMENT_PLAN")


def _parse_segment_prompts(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        raise ValueError("分段提示词不能为空")
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
        raise ValueError("没有解析到分段提示词；请使用 JSON 数组或 --- SEGMENT --- 分隔")
    return prompts


def _inject_continuity_instruction(prompt: str, overlap_frames: int) -> tuple[str, bool]:
    duration = overlap_frames / H3_FPS
    instruction = (
        f" The opening 00:00.000-00:{duration:06.3f} is a fixed latent continuation "
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
        raise ValueError("有限分段需要完整素材规划；请不要给素材规划台连接“提示词序号”")
    timeline, selected, configured_count = _timeline_for_prompt_index(
        source["timeline"], segment_number
    )
    result = copy.deepcopy(source)
    result["timeline"] = timeline
    result["prompt_index"] = selected
    result["segment_count"] = configured_count
    return result


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
            f"素材规划台配置了 {configured_count} 段，但有限分段设置为 {count} 段；请保持一致"
        )
    prompts = _parse_segment_prompts(segment_prompts)
    if len(prompts) != count:
        raise ValueError(
            f"有限分段设置为 {count} 段，但解析到 {len(prompts)} 段提示词；请严格保持一致"
        )
    actual_overlap = _valid_guide_frames(int(overlap_frames))
    prepared = []
    for index, prompt in enumerate(prompts):
        if index > 0 and inject_continuity:
            prompt, injected = _inject_continuity_instruction(prompt, actual_overlap)
            if not injected:
                raise ValueError(
                    f"第 {index + 1} 段未在标准 H3 字段中找到 [Shot 1]，无法注入连续性说明"
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
        raise ValueError("finite_plan 必须来自 MiniMax H3 有限分段展开")
    count = int(value.get("segment_count") or 0)
    prompts = value.get("prompts")
    if count < 1 or not isinstance(prompts, list) or len(prompts) != count:
        raise ValueError("有限分段规划数据不完整，请重新执行有限分段展开")
    return value


class MiniMaxH3FiniteSegmentExpansion(io.ComfyNode):
    """Validate prompts/media assignments and produce a reusable finite plan."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteSegmentExpansion",
            display_name="MiniMax H3 有限分段展开",
            category="MiniMax H3/长视频",
            description=(
                "只负责解析提示词、校验段数、匹配每段素材并生成有限分段规划；"
                "不包含模型、采样器、调度器或采样过程。"
            ),
            inputs=[
                TimelinePlan.Input("plan", display_name="素材规划参数"),
                io.String.Input("segment_prompts", multiline=True),
                io.Int.Input("segment_count", display_name="分段数量", default=3, min=1, max=12),
                io.Int.Input(
                    "overlap_frames", display_name="重叠帧", default=22,
                    min=1, max=362, tooltip="自动向下对齐为 1 或 5/22/39/56…帧。",
                ),
                io.Boolean.Input(
                    "inject_continuity_instruction", display_name="注入开头连续性说明", default=True,
                ),
            ],
            outputs=[
                FiniteSegmentPlan.Output(display_name="有限分段规划"),
                io.Int.Output(display_name="实际重叠帧"),
                io.String.Output(display_name="规划状态"),
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
            f"已规划 {finite['segment_count']} 段；实际重叠 {overlap} 帧 "
            f"({overlap / H3_FPS:.3f} 秒)；本节点不执行采样。"
        )
        return io.NodeOutput(finite, overlap, status)


class MiniMaxH3FiniteLatentContinuation(io.ComfyNode):
    """Internal finite-graph helper that carries the previous AV latent tail."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteLatentContinuation",
            display_name="MiniMax H3 有限分段 Latent 续接（内部）",
            category="MiniMax H3/内部",
            is_dev_only=True,
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("target_latent"),
                io.Int.Input("iteration", force_input=True),
                io.Latent.Input("previous_latent", optional=True),
                io.Int.Input("overlap_frames", default=22, min=1, max=362),
                io.Boolean.Input("continue_audio_latent", default=True),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(display_name="目标 latent"),
                io.Int.Output(display_name="实际重叠帧"),
            ],
        )

    @classmethod
    def execute(
        cls, positive, target_latent, iteration, overlap_frames,
        continue_audio_latent, previous_latent=None,
    ):
        actual_overlap = _valid_guide_frames(int(overlap_frames))
        if int(iteration) <= 0:
            return io.NodeOutput(positive, target_latent, actual_overlap)
        if previous_latent is None:
            raise ValueError("第 2 段及以后缺少上一段 sampled latent")
        keyframe, details = _build_direct_latent_keyframe(
            target_latent=target_latent,
            source_latent=previous_latent,
            guide_frames=actual_overlap,
            frame_idx=0,
            include_audio=bool(continue_audio_latent),
        )
        masked_target, _ = _apply_linear_temporal_noise_mask(
            target_latent=target_latent,
            source_latent=previous_latent,
            guide_frames=actual_overlap,
            include_audio=bool(continue_audio_latent),
        )
        keyframes = list(positive[0][1].get("minimax_keyframes", []))
        keyframes.append(keyframe)
        conditioned = node_helpers.conditioning_set_values(
            positive, {"minimax_keyframes": keyframes}
        )
        return io.NodeOutput(conditioned, masked_target, details["frames"])


class MiniMaxH3FiniteSegmentFinalize(io.ComfyNode):
    """Internal finite-graph helper that removes decoded overlap."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteSegmentFinalize",
            display_name="MiniMax H3 有限分段去重（内部）",
            category="MiniMax H3/内部",
            is_dev_only=True,
            inputs=[
                io.Latent.Input("sampled_latent"),
                io.Image.Input("images"),
                io.Int.Input("iteration", force_input=True),
                io.Int.Input("overlap_frames", default=22, min=1, max=362),
                io.Audio.Input("audio", optional=True),
            ],
            outputs=[
                io.Latent.Output(display_name="完整 latent"),
                io.Image.Output(display_name="去重画面"),
                io.Audio.Output(display_name="去重音频"),
            ],
        )

    @classmethod
    def execute(cls, sampled_latent, images, iteration, overlap_frames, audio=None):
        trim_frames = 0 if int(iteration) <= 0 else _valid_guide_frames(int(overlap_frames))
        if images.shape[0] <= trim_frames:
            raise ValueError(f"本段只有 {images.shape[0]} 帧，无法删除 {trim_frames} 帧重叠区")
        trimmed_images = images[trim_frames:].clone() if trim_frames else images
        trimmed_audio = audio
        if audio is not None:
            waveform = audio.get("waveform")
            sample_rate = int(audio.get("sample_rate", 0))
            if waveform is None or sample_rate <= 0:
                raise ValueError("audio 必须包含 waveform 和有效 sample_rate")
            trim_samples = round((trim_frames / H3_FPS) * sample_rate)
            if waveform.shape[-1] <= trim_samples:
                raise ValueError("本段音频长度不足以删除对应重叠区")
            trimmed_audio = dict(audio)
            trimmed_audio["waveform"] = (
                waveform[..., trim_samples:].clone() if trim_samples else waveform
            )
        return io.NodeOutput(sampled_latent, trimmed_images, trimmed_audio)


class MiniMaxH3FiniteSegmentSampler(io.ComfyNode):
    """Expand a finite plan into a standard acyclic sampling graph."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3FiniteSegmentSampler",
            display_name="MiniMax H3 有限分段采样",
            category="MiniMax H3/长视频",
            description=(
                "读取有限分段规划并展开普通无环采样图。采样器与调度器仍由外部节点提供，"
                "不依赖 Loop / Loop Variable / Close Loop。"
            ),
            enable_expand=True,
            inputs=[
                io.Model.Input("model"),
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                FiniteSegmentPlan.Input("finite_plan", display_name="有限分段规划"),
                io.Sampler.Input("sampler"),
                io.Sigmas.Input("sigmas"),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True),
                io.Boolean.Input("increment_seed", display_name="每段递增种子", default=True),
                io.Boolean.Input("continue_audio_latent", display_name="延续音频 latent", default=True),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="match"),
            ],
            outputs=[
                io.Latent.Output(display_name="末段 sampled latent"),
                io.Image.Output(display_name="合并画面"),
                io.Audio.Output(display_name="合并音频"),
                io.String.Output(display_name="采样状态"),
            ],
        )

    @classmethod
    def execute(
        cls, model, clip, vae, audio_vae, finite_plan, sampler, sigmas, seed,
        increment_seed, continue_audio_latent, ref_image_size="match",
    ):
        finite = _require_finite_plan(finite_plan)
        graph = GraphBuilder()
        previous_latent = None
        merged_images = None
        merged_audio = None
        last_sampled = None
        overlap = int(finite["overlap_frames"])

        for index, prompt in enumerate(finite["prompts"]):
            number = index + 1
            encoder = graph.node(
                "MiniMaxH3TimelineEncoder", id=f"encode_{number}",
                clip=clip, vae=vae, audio_vae=audio_vae,
                plan=_plan_for_segment(finite["source_plan"], number),
                prompt=prompt, ref_image_size=ref_image_size,
            )
            continuation_inputs = {
                "positive": encoder.out(0), "target_latent": encoder.out(1),
                "iteration": index, "overlap_frames": overlap,
                "continue_audio_latent": bool(continue_audio_latent),
            }
            if previous_latent is not None:
                continuation_inputs["previous_latent"] = previous_latent
            continuation = graph.node(
                "MiniMaxH3FiniteLatentContinuation", id=f"continue_{number}",
                **continuation_inputs,
            )
            noise_seed = ((int(seed) + index) % (1 << 64)) if increment_seed else int(seed)
            noise = graph.node("RandomNoise", id=f"noise_{number}", noise_seed=noise_seed)
            guider = graph.node(
                "BasicGuider", id=f"guider_{number}", model=model,
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
            )
            current_images, current_audio = finalized.out(1), finalized.out(2)
            if merged_images is None:
                merged_images, merged_audio = current_images, current_audio
            else:
                image_join = graph.node(
                    "ImageBatch", id=f"join_images_{number}",
                    image1=merged_images, image2=current_images,
                )
                audio_join = graph.node(
                    "AudioConcat", id=f"join_audio_{number}",
                    audio1=merged_audio, audio2=current_audio, direction="after",
                )
                merged_images, merged_audio = image_join.out(0), audio_join.out(0)
            previous_latent = sampled.out(0)
            last_sampled = sampled.out(0)

        status = (
            f"已展开并采样 {finite['segment_count']} 段；实际重叠 {overlap} 帧；"
            f"音频 latent {'参与延续' if continue_audio_latent else '不参与延续'}。"
        )
        return io.NodeOutput(
            last_sampled, merged_images, merged_audio, status, expand=graph.finalize()
        )
