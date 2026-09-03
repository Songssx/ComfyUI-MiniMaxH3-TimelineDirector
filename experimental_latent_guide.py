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
        raise ValueError(f"{label} must be a nested MiniMax H3 video-and-audio latent")
    tensors = getattr(samples, "tensors", ())
    if len(tensors) != 2 or tensors[0].ndim != 5 or tensors[0].shape[1] != 24:
        raise ValueError(f"{label} is not a valid MiniMax H3 AV latent")
    if tensors[1].ndim != 4 or tensors[1].shape[1] != 32:
        raise ValueError(f"{label} does not contain a valid MiniMax H3 audio latent")
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
            "Direct Latent Guide requires matching latent spatial dimensions; "
            f"got {tuple(source_video.shape[3:])} -> {tuple(target_video.shape[3:])}"
        )

    actual_frames = _valid_guide_frames(int(guide_frames))
    guide_tokens = _video_latent_t(actual_frames)
    if guide_tokens > source_video.shape[2]:
        raise ValueError(
            f"The source latent has only {source_video.shape[2]} video tokens; "
            f"{actual_frames} frames require {guide_tokens} tokens"
        )

    target_frames = _frame_count(target_video)
    resolved = int(frame_idx) if frame_idx >= 0 else target_frames + int(frame_idx)
    if resolved < 0 or resolved + actual_frames > target_frames:
        raise ValueError(
            f"A {actual_frames}-frame latent guide starting at frame_idx={frame_idx} "
            f"does not fit in a {target_frames}-frame target"
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
            raise ValueError("The source or target H3 audio latent is too short for the fixed audio overlap")
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
    gradient=True,
    audio_soft_release=False,
):
    """Copy the previous tail and configure denoising inside the Guide interval.

    H3 samples video and audio as a nested latent.  The sampler interprets a
    noise-mask value of 0 as preserved input and 1 as fully denoised.  Keep the
    mask compact (one channel and 1x1 spatial size); ComfyUI expands it to each
    stream's latent shape immediately before sampling.  With ``gradient``
    enabled the Guide interval fades from 0 to 1; when disabled it stays at 0
    so the copied Guide latent is fully preserved.  The area after the Guide
    interval remains 1 in both modes.
    """

    target_video, target_audio = _h3_streams(target_latent, "target_latent")
    source_video, source_audio = _h3_streams(source_latent, "source_latent")
    if target_video.shape[3:] != source_video.shape[3:]:
        raise ValueError(
            "The linear temporal mask requires matching latent spatial dimensions; "
            f"got {tuple(source_video.shape[3:])} -> {tuple(target_video.shape[3:])}"
        )

    actual_frames = _valid_guide_frames(int(guide_frames))
    video_tokens = _video_latent_t(actual_frames)
    if video_tokens > source_video.shape[2] or video_tokens > target_video.shape[2]:
        raise ValueError(
            f"The source or target latent cannot hold a {actual_frames}-frame linear overlap "
            f"({video_tokens} video tokens required)"
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
    video_ramp = (
        torch.linspace(
            0.0,
            1.0,
            steps=video_tokens,
            dtype=video_mask.dtype,
            device=video_mask.device,
        )
        if gradient
        else torch.zeros(video_tokens, dtype=video_mask.dtype, device=video_mask.device)
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
            raise ValueError("The source or target H3 audio latent is too short for the linear audio overlap")
        audio_tail = source_audio[:1, :, :, -audio_tokens:].to(
            device=audio.device, dtype=audio.dtype
        )
        audio[..., :audio_tokens] = audio_tail.expand(audio.shape[0], -1, -1, -1)
        if audio_soft_release:
            audio_ramp = torch.zeros(
                audio_tokens, dtype=audio_mask.dtype, device=audio_mask.device
            )
            release_tokens = min(8, audio_tokens)
            indices = torch.arange(
                1, release_tokens + 1,
                dtype=audio_mask.dtype,
                device=audio_mask.device,
            )
            audio_ramp[-release_tokens:] = 0.5 - 0.5 * torch.cos(
                torch.pi * indices / float(release_tokens)
            )
        elif gradient:
            audio_ramp = torch.linspace(
                0.0,
                1.0,
                steps=audio_tokens,
                dtype=audio_mask.dtype,
                device=audio_mask.device,
            )
        else:
            audio_ramp = torch.zeros(
                audio_tokens, dtype=audio_mask.dtype, device=audio_mask.device
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
        "gradient": bool(gradient),
        "audio_soft_release": bool(audio_soft_release and include_audio),
    }


class MiniMaxH3AddLatentGuide(io.ComfyNode):
    """Anchor a sampled H3 latent tail without an RGB decode/encode round trip."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3AddLatentGuide",
            display_name="MiniMax H3 Direct Latent Guide (Experimental)",
            category="MiniMax H3/Experimental",
            description=(
                "Copy a valid temporal block from the tail of a sampled MiniMax H3 AV latent "
                "directly into another target latent for RGB/VAE round-trip A/B testing."
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
                    tooltip="Requested tail-frame count; aligned down to 1 or 17k+5 (5/22/39...).",
                ),
                io.Int.Input(
                    "frame_idx",
                    default=0,
                    min=-9999,
                    max=9999,
                    tooltip="Start frame at which the latent block is fixed in the target segment.",
                ),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.String.Output(display_name="Experiment Details"),
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
            f"Direct latent guide: requested {guide_frames} frames, used {details['frames']} frames / "
            f"{details['video_tokens']} tokens, fixed at target frame {details['frame_idx']}; "
            "no RGB or VAE re-encoding was performed."
        )
        return io.NodeOutput(conditioned, report)


class MiniMaxH3VisualDifferenceMetrics(io.ComfyNode):
    """Report lightweight objective differences between two decoded videos."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3VisualDifferenceMetrics",
            display_name="MiniMax H3 Video Difference Metrics (Experimental)",
            category="MiniMax H3/Experimental",
            description="Compare two RGB frame batches and report MAE, MSE, PSNR, means, saturation, and amplified differences.",
            inputs=[
                io.Image.Input("reference"),
                io.Image.Input("comparison"),
                io.Float.Input("difference_gain", default=4.0, min=1.0, max=32.0, step=0.5),
            ],
            outputs=[
                io.String.Output(display_name="Metrics Report"),
                io.Image.Output(display_name="Amplified Difference"),
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
            raise ValueError("The video comparison has no common frames or pixels")

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
                f"Common range: {frames} frames, {width}x{height}",
                f"MAE={mae:.8f}  MSE={mse:.8f}  PSNR={psnr:.3f} dB",
                "Reference RGB mean=" + ", ".join(f"{v:.6f}" for v in ref_mean.tolist()),
                "Comparison RGB mean=" + ", ".join(f"{v:.6f}" for v in cmp_mean.tolist()),
                f"Mean saturation: reference={ref_sat:.6f}  comparison={cmp_sat:.6f}  delta={cmp_sat-ref_sat:+.6f}",
                f"Clipped-pixel ratio: reference={ref_clip:.6f}  comparison={cmp_clip:.6f}  delta={cmp_clip-ref_clip:+.6f}",
            ]
        )
        difference = delta.abs().mul(float(difference_gain)).clamp(0, 1)
        return io.NodeOutput(report, difference)
