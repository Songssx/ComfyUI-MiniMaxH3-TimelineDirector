"""Experimental MiniMax H3 nodes used for latent continuity A/B tests.

These nodes deliberately live outside the production timeline implementation.
They make it possible to compare the native RGB -> VAE encode guide path with a
direct crop of an already sampled H3 video latent.
"""

from __future__ import annotations

import math

import torch
import node_helpers
from comfy.ldm.minimax.model import FRAME_PER_TOKEN
from comfy.nested_tensor import NestedTensor
from comfy_api.latest import io


def _h3_streams(latent, label):
    samples = latent.get("samples") if isinstance(latent, dict) else None
    if samples is None or not getattr(samples, "is_nested", False):
        raise ValueError(f"{label} 必须是 MiniMax H3 的视频+音频嵌套 latent")
    tensors = getattr(samples, "tensors", ())
    if len(tensors) != 2 or tensors[0].ndim != 5 or tensors[0].shape[1] != 24:
        raise ValueError(f"{label} 不是有效的 MiniMax H3 AV latent")
    if tensors[1].ndim != 4 or tensors[1].shape[1] != 32:
        raise ValueError(f"{label} 的音频流不是有效的 MiniMax H3 audio latent")
    return tensors[0], tensors[1]


def _frame_count(video_latent):
    return sum(FRAME_PER_TOKEN[k % 5] for k in range(video_latent.shape[2]))


def _valid_guide_frames(requested):
    if requested < 5:
        return 1
    while requested % 17 != 5:
        requested -= 1
    return max(1, requested)


def _video_latent_t(frame_count):
    return 2 if frame_count <= 5 else ((frame_count - 5) // 17) * 5 + 2


def _build_direct_latent_keyframe(
    target_latent,
    source_latent,
    guide_frames,
    frame_idx=0,
    include_audio=False,
):
    target_video, target_audio = _h3_streams(target_latent, "target_latent")
    source_video, source_audio = _h3_streams(source_latent, "source_latent")
    if target_video.shape[3:] != source_video.shape[3:]:
        raise ValueError(
            "直接 Latent Guide 要求两段视频的 latent 空间尺寸一致；"
            f"当前为 {tuple(source_video.shape[3:])} -> {tuple(target_video.shape[3:])}"
        )

    actual_frames = _valid_guide_frames(int(guide_frames))
    guide_tokens = _video_latent_t(actual_frames)
    if guide_tokens > source_video.shape[2]:
        raise ValueError(
            f"源 latent 只有 {source_video.shape[2]} 个视频 token，"
            f"不足以截取 {actual_frames} 帧（需要 {guide_tokens} token）"
        )

    target_frames = _frame_count(target_video)
    resolved = int(frame_idx) if frame_idx >= 0 else target_frames + int(frame_idx)
    if resolved < 0 or resolved + actual_frames > target_frames:
        raise ValueError(
            f"{actual_frames} 帧 latent guide 从 frame_idx={frame_idx} 开始，"
            f"无法放入共 {target_frames} 帧的目标视频"
        )

    tail = source_video[:1, :, -guide_tokens:, :, :].clone()
    keyframe = {"resolved_frame_index": resolved, "latent": tail}
    audio_tokens = 0
    if include_audio:
        audio_tokens = round(actual_frames * 40 / 24)
        audio_tokens = min(audio_tokens, source_audio.shape[-1])
        max_target_audio = int(target_audio.shape[-1] - round(resolved * 40 / 24))
        audio_tokens = min(audio_tokens, max_target_audio)
        if audio_tokens < 1:
            raise ValueError("目标或源 H3 audio latent 不足以放置循环音频固定区")
        keyframe["audio_latent"] = source_audio[:1, :, :, -audio_tokens:].clone()

    return keyframe, {
        "frames": actual_frames,
        "video_tokens": guide_tokens,
        "audio_tokens": audio_tokens,
        "frame_idx": resolved,
    }


def _apply_linear_temporal_noise_mask(
    target_latent,
    source_latent,
    guide_frames,
    include_audio=False,
):
    """Copy the previous tail into the target and fade denoising from 0 to 1.

    H3 samples video and audio as a nested latent.  The sampler interprets a
    noise-mask value of 0 as preserved input and 1 as fully denoised.  Keep the
    mask compact (one channel and 1x1 spatial size); ComfyUI expands it to each
    stream's latent shape immediately before sampling.
    """

    target_video, target_audio = _h3_streams(target_latent, "target_latent")
    source_video, source_audio = _h3_streams(source_latent, "source_latent")
    if target_video.shape[3:] != source_video.shape[3:]:
        raise ValueError(
            "线性时间遮罩要求两段视频的 latent 空间尺寸一致；"
            f"当前为 {tuple(source_video.shape[3:])} -> {tuple(target_video.shape[3:])}"
        )

    actual_frames = _valid_guide_frames(int(guide_frames))
    video_tokens = _video_latent_t(actual_frames)
    if video_tokens > source_video.shape[2] or video_tokens > target_video.shape[2]:
        raise ValueError(
            f"源或目标 latent 不足以放置 {actual_frames} 帧线性重叠区"
            f"（需要 {video_tokens} 个视频 token）"
        )

    video = target_video.clone()
    video_tail = source_video[:1, :, -video_tokens:, :, :].to(
        device=video.device, dtype=video.dtype
    )
    video[:, :, :video_tokens, :, :] = video_tail.expand(
        video.shape[0], -1, -1, -1, -1
    )
    video_mask = torch.ones(
        (1, 1, target_video.shape[2], 1, 1),
        dtype=torch.float32,
        device=target_video.device,
    )
    video_ramp = torch.linspace(
        0.0,
        1.0,
        steps=video_tokens,
        dtype=video_mask.dtype,
        device=video_mask.device,
    )
    video_mask[:, :, :video_tokens, :, :] = video_ramp.reshape(1, 1, -1, 1, 1)

    audio = target_audio.clone()
    audio_mask = torch.ones(
        (1, 1, 1, target_audio.shape[-1]),
        dtype=torch.float32,
        device=target_audio.device,
    )
    audio_tokens = 0
    if include_audio:
        audio_tokens = min(
            round(actual_frames * 40 / 24),
            source_audio.shape[-1],
            target_audio.shape[-1],
        )
        if audio_tokens < 1:
            raise ValueError("目标或源 H3 audio latent 不足以放置线性音频重叠区")
        audio_tail = source_audio[:1, :, :, -audio_tokens:].to(
            device=audio.device, dtype=audio.dtype
        )
        audio[..., :audio_tokens] = audio_tail.expand(audio.shape[0], -1, -1, -1)
        audio_ramp = torch.linspace(
            0.0,
            1.0,
            steps=audio_tokens,
            dtype=audio_mask.dtype,
            device=audio_mask.device,
        )
        audio_mask[..., :audio_tokens] = audio_ramp.reshape(1, 1, 1, -1)

    output = dict(target_latent)
    output["samples"] = NestedTensor((video, audio))
    output["noise_mask"] = NestedTensor((video_mask, audio_mask))
    return output, {
        "frames": actual_frames,
        "video_tokens": video_tokens,
        "audio_tokens": audio_tokens,
        "video_mask_start": float(video_ramp[0].item()),
        "video_mask_end": float(video_ramp[-1].item()),
    }


class MiniMaxH3AddLatentGuide(io.ComfyNode):
    """Anchor a sampled H3 latent tail without an RGB decode/encode round trip."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3AddLatentGuide",
            display_name="MiniMax H3 直接 Latent Guide（实验）",
            category="MiniMax H3/实验",
            description=(
                "从已采样的 MiniMax H3 AV latent 尾部截取合法视频时间块，直接固定到另一个 "
                "H3 目标 latent。用于和原生 RGB→VAE Encode Guide 做色彩累计 A/B 测试。"
            ),
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("target_latent"),
                io.Latent.Input("source_latent"),
                io.Int.Input(
                    "guide_frames",
                    default=22,
                    min=1,
                    max=362,
                    step=1,
                    tooltip="请求的尾部像素帧数；自动向下对齐为 1 或 17k+5（5/22/39…）。",
                ),
                io.Int.Input(
                    "frame_idx",
                    default=0,
                    min=-9999,
                    max=9999,
                    tooltip="在第二段目标视频中固定这段 latent 的起始帧。",
                ),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.String.Output(display_name="实验信息"),
            ],
        )

    @classmethod
    def execute(cls, positive, target_latent, source_latent, guide_frames, frame_idx):
        keyframe, details = _build_direct_latent_keyframe(
            target_latent,
            source_latent,
            guide_frames,
            frame_idx,
            include_audio=False,
        )
        keyframes = list(positive[0][1].get("minimax_keyframes", []))
        keyframes.append(keyframe)
        conditioned = node_helpers.conditioning_set_values(
            positive, {"minimax_keyframes": keyframes}
        )
        report = (
            f"直接 latent guide：请求 {guide_frames} 帧，实际 {details['frames']} 帧 / "
            f"{details['video_tokens']} token，固定到目标第 {details['frame_idx']} 帧；"
            "未经过 RGB 与 VAE 重编码。"
        )
        return io.NodeOutput(conditioned, report)


class MiniMaxH3VisualDifferenceMetrics(io.ComfyNode):
    """Report lightweight objective differences between two decoded videos."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3VisualDifferenceMetrics",
            display_name="MiniMax H3 视频差异指标（实验）",
            category="MiniMax H3/实验",
            description="比较两批 RGB 视频帧，输出 MAE/MSE/PSNR、均值、饱和度和放大差异图。",
            inputs=[
                io.Image.Input("reference"),
                io.Image.Input("comparison"),
                io.Float.Input("difference_gain", default=4.0, min=1.0, max=32.0, step=0.5),
            ],
            outputs=[
                io.String.Output(display_name="指标报告"),
                io.Image.Output(display_name="放大差异"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, reference, comparison, difference_gain):
        frames = min(reference.shape[0], comparison.shape[0])
        height = min(reference.shape[1], comparison.shape[1])
        width = min(reference.shape[2], comparison.shape[2])
        channels = min(reference.shape[3], comparison.shape[3], 3)
        if frames < 1 or height < 1 or width < 1 or channels < 1:
            raise ValueError("视频差异比较没有可用的共同帧或像素")

        ref = reference[:frames, :height, :width, :channels].float().clamp(0, 1)
        cmp = comparison[:frames, :height, :width, :channels].float().clamp(0, 1)
        delta = cmp - ref
        mae = delta.abs().mean().item()
        mse = delta.square().mean().item()
        psnr = float("inf") if mse == 0 else -10.0 * math.log10(mse)

        def stats(x):
            rgb_mean = x.mean(dim=(0, 1, 2))
            high = x.max(dim=-1).values
            low = x.min(dim=-1).values
            saturation = torch.where(high > 1e-6, (high - low) / high, torch.zeros_like(high))
            clipped = ((x <= (1.0 / 255.0)) | (x >= (254.0 / 255.0))).float().mean()
            return rgb_mean, saturation.mean().item(), clipped.item()

        ref_mean, ref_sat, ref_clip = stats(ref)
        cmp_mean, cmp_sat, cmp_clip = stats(cmp)
        report = "\n".join(
            [
                f"共同范围：{frames} 帧，{width}x{height}",
                f"MAE={mae:.8f}  MSE={mse:.8f}  PSNR={psnr:.3f} dB",
                "参考 RGB 均值=" + ", ".join(f"{v:.6f}" for v in ref_mean.tolist()),
                "对比 RGB 均值=" + ", ".join(f"{v:.6f}" for v in cmp_mean.tolist()),
                f"平均饱和度：参考={ref_sat:.6f}  对比={cmp_sat:.6f}  变化={cmp_sat-ref_sat:+.6f}",
                f"极值像素比例：参考={ref_clip:.6f}  对比={cmp_clip:.6f}  变化={cmp_clip-ref_clip:+.6f}",
            ]
        )
        difference = delta.abs().mul(float(difference_gain)).clamp(0, 1)
        return io.NodeOutput(report, difference)
