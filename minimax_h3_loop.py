"""MiniMax H3 long-video helpers for ComfyUI's generic Loop nodes.

The loop scheduler remains owned by ComfyUI.  These nodes only adapt a carried
H3 AV latent into a direct guide and remove the duplicated overlap from decoded
video/audio chunks before they are accumulated.
"""

from __future__ import annotations

import json
import re

import torch
import node_helpers
from comfy_api.latest import io

from .experimental_latent_guide import (
    _build_direct_latent_keyframe,
    _valid_guide_frames,
)

H3_FPS = 24


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
        raise ValueError("没有解析到任何分段提示词；请使用 JSON 数组或 --- SEGMENT --- 分隔")
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


class MiniMaxH3LoopPromptSelector(io.ComfyNode):
    """Select the current segment prompt and annotate its fixed opening overlap."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LoopPromptSelector",
            display_name="MiniMax H3 循环分段提示词",
            category="MiniMax H3/长视频循环",
            description=(
                "按照 Loop 的 iteration 选择本轮 H3 提示词。支持 JSON 字符串数组，或使用 "
                "--- SEGMENT --- 独占行分隔；提示词不足时重复最后一段。"
            ),
            inputs=[
                io.Int.Input("iteration", force_input=True),
                io.String.Input("segment_prompts", multiline=True),
                io.Int.Input(
                    "overlap_frames",
                    default=22,
                    min=1,
                    max=362,
                    step=1,
                    tooltip="自动向下对齐为 1 或 17k+5 帧，并与 Latent Guide 保持一致。",
                ),
                io.Boolean.Input(
                    "inject_continuity_instruction",
                    default=True,
                    tooltip="第二段起，把固定区说明插入 integrated_multimodal_description/detailed_description 的 [Shot 1] 后。",
                ),
            ],
            outputs=[
                io.String.Output(display_name="本段提示词"),
                io.Int.Output(display_name="提示词序号"),
                io.String.Output(display_name="提示词状态"),
            ],
        )

    @classmethod
    def execute(
        cls,
        iteration,
        segment_prompts,
        overlap_frames,
        inject_continuity_instruction,
    ):
        prompts = _parse_segment_prompts(segment_prompts)
        requested_index = max(0, int(iteration))
        selected_index = min(requested_index, len(prompts) - 1)
        selected = prompts[selected_index]
        actual_overlap = _valid_guide_frames(int(overlap_frames))
        injected = False
        if requested_index > 0 and inject_continuity_instruction:
            selected, injected = _inject_continuity_instruction(selected, actual_overlap)

        repeated = requested_index >= len(prompts)
        status = (
            f"循环第 {requested_index + 1} 段 → 提示词 {selected_index + 1}/{len(prompts)}；"
            f"固定区 {actual_overlap} 帧（{actual_overlap / H3_FPS:.3f} 秒）；"
            f"{'已插入 Shot 1 连续性说明' if injected else '未插入连续性说明'}"
        )
        if repeated:
            status += "；提示词数量不足，正在重复最后一段"
        if requested_index > 0 and inject_continuity_instruction and not injected:
            status += "；警告：未找到标准 H3 字段中的 [Shot 1]"
        return io.NodeOutput(selected, selected_index + 1, status)


class MiniMaxH3LoopLatentGuide(io.ComfyNode):
    """Apply the previous iteration's AV latent tail to the current H3 target."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LoopLatentGuide",
            display_name="MiniMax H3 Latent 循环续段",
            category="MiniMax H3/长视频循环",
            description=(
                "连接 Loop Variable 的 current_value。第一轮原样通过；后续轮次把上一轮完整 "
                "H3 AV latent 的尾部直接固定到本轮开头，不经过 RGB 解码与 VAE 重编码。"
            ),
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("target_latent"),
                io.Boolean.Input("is_first", force_input=True),
                io.Int.Input("iteration", force_input=True),
                io.Latent.Input("previous_latent", optional=True),
                io.Int.Input(
                    "overlap_frames",
                    default=22,
                    min=1,
                    max=362,
                    step=1,
                    tooltip="上一段尾部参与下一段固定的帧数；自动对齐为 1 或 5/22/39/56…帧。",
                ),
                io.Boolean.Input(
                    "continue_audio_latent",
                    default=True,
                    tooltip="同时固定上一段尾部对应的 H3 音频 latent。",
                ),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(display_name="目标 latent"),
                io.Int.Output(display_name="实际重叠帧"),
                io.String.Output(display_name="循环状态"),
            ],
        )

    @classmethod
    def execute(
        cls,
        positive,
        target_latent,
        is_first,
        iteration,
        overlap_frames,
        continue_audio_latent,
        previous_latent=None,
    ):
        actual_overlap = _valid_guide_frames(int(overlap_frames))
        loop_index = max(0, int(iteration))
        if bool(is_first) or loop_index == 0:
            status = (
                f"循环第 1 段：没有使用上一段 latent；本轮采样结果将作为下一轮反馈。"
                f"后续固定区为 {actual_overlap} 帧。"
            )
            return io.NodeOutput(positive, target_latent, actual_overlap, status)
        if previous_latent is None:
            raise ValueError(
                "第 2 段及以后需要 previous_latent；请把 Sampler 的完整 H3 latent 经由 "
                "Loop Variable 反馈到本节点"
            )

        keyframe, details = _build_direct_latent_keyframe(
            target_latent=target_latent,
            source_latent=previous_latent,
            guide_frames=actual_overlap,
            frame_idx=0,
            include_audio=bool(continue_audio_latent),
        )
        keyframes = list(positive[0][1].get("minimax_keyframes", []))
        keyframes.append(keyframe)
        conditioned = node_helpers.conditioning_set_values(
            positive, {"minimax_keyframes": keyframes}
        )
        status = (
            f"循环第 {loop_index + 1} 段：直接复用上一段尾部 {details['frames']} 帧 / "
            f"{details['video_tokens']} 个视频 token"
        )
        if details["audio_tokens"]:
            status += f" / {details['audio_tokens']} 个音频 token"
        else:
            status += "；未固定音频 latent"
        return io.NodeOutput(conditioned, target_latent, details["frames"], status)


class MiniMaxH3LoopSegmentFinalize(io.ComfyNode):
    """Return the full latent for feedback and trim duplicate decoded overlap."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LoopSegmentFinalize",
            display_name="MiniMax H3 循环片段去重",
            category="MiniMax H3/长视频循环",
            description=(
                "完整 sampled_latent 反馈给 Loop Variable；第一段保留全部解码内容，第二段起 "
                "删除开头的固定重叠画面与等时长音频，再交给 Close Loop 或 Accumulate Save Video。"
            ),
            inputs=[
                io.Latent.Input("sampled_latent"),
                io.Image.Input("images"),
                io.Int.Input("iteration", force_input=True),
                io.Int.Input(
                    "overlap_frames",
                    default=22,
                    min=1,
                    max=362,
                    step=1,
                ),
                io.Audio.Input("audio", optional=True),
            ],
            outputs=[
                io.Latent.Output(display_name="反馈 latent"),
                io.Image.Output(display_name="去重画面"),
                io.Audio.Output(display_name="去重音频"),
                io.Int.Output(display_name="保留帧数"),
                io.String.Output(display_name="去重状态"),
            ],
        )

    @classmethod
    def execute(cls, sampled_latent, images, iteration, overlap_frames, audio=None):
        loop_index = max(0, int(iteration))
        actual_overlap = _valid_guide_frames(int(overlap_frames))
        trim_frames = 0 if loop_index == 0 else actual_overlap
        if images.shape[0] <= trim_frames:
            raise ValueError(
                f"本轮只有 {images.shape[0]} 帧，无法删除 {trim_frames} 帧重叠区"
            )
        trimmed_images = images[trim_frames:].clone() if trim_frames else images

        trimmed_audio = audio
        trim_samples = 0
        if audio is not None:
            waveform = audio.get("waveform")
            sample_rate = int(audio.get("sample_rate", 0))
            if waveform is None or sample_rate <= 0:
                raise ValueError("audio 必须包含 waveform 和有效的 sample_rate")
            trim_samples = round((trim_frames / H3_FPS) * sample_rate)
            if waveform.shape[-1] <= trim_samples:
                raise ValueError(
                    f"本轮音频只有 {waveform.shape[-1]} 个采样，无法删除 {trim_samples} 个重叠采样"
                )
            trimmed_audio = dict(audio)
            trimmed_audio["waveform"] = (
                waveform[..., trim_samples:].clone() if trim_samples else waveform
            )

        kept_frames = int(trimmed_images.shape[0])
        status = (
            f"循环第 {loop_index + 1} 段：保留 {kept_frames}/{images.shape[0]} 帧；"
            f"删除 {trim_frames} 帧重叠画面"
        )
        if audio is not None:
            status += f"和 {trim_samples} 个音频采样"
        return io.NodeOutput(
            sampled_latent,
            trimmed_images,
            trimmed_audio,
            kept_frames,
            status,
        )
