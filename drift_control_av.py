"""Schedule-matched prefix masks for experimental MiniMax H3 continuation.

The implementation is adapted from ethanfel/ComfyUI-MiniMaxH3-Contex-Loop's
Drift-Control AV v1 (GPL-3.0).  It keeps the saved predecessor latent clean and
changes only the disposable video prefix used by the active sampling run.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import torch


DRIFT_CONTROL_VIDEO_STEPS = 12
DRIFT_CONTROL_MATCHED_STEPS = 8
DRIFT_CONTROL_TAPER_STEPS = 4
_WRAPPER_KEY = "minimax_h3_timeline_drift_control_av"


def _schedule_values(sigmas: Any) -> tuple[float, ...]:
    """Return finite, non-negative scheduler values in descending order."""
    if torch.is_tensor(sigmas):
        values: Iterable[Any] = sigmas.detach().float().reshape(-1).cpu()
    else:
        values = sigmas or ()
    normalized = []
    for value in values:
        number = float(value)
        if math.isfinite(number) and number >= 0.0:
            normalized.append(number)
    return tuple(sorted(set(normalized), reverse=True))


def drift_control_step_count(sigmas: Any) -> int:
    values = _schedule_values(sigmas)
    return max(0, len(values) - 1)


def next_schedule_sigma(current_sigma: float, sigmas: Any) -> float:
    current = float(current_sigma)
    if not math.isfinite(current) or current <= 0.0:
        return 0.0
    tolerance = max(1e-7, abs(current) * 1e-6)
    for candidate in _schedule_values(sigmas):
        if candidate < current - tolerance:
            return candidate
    return 0.0


def matched_noise_ratio(current_sigma: float, sigmas: Any) -> float:
    current = float(current_sigma)
    if not math.isfinite(current) or current <= 0.0:
        return 0.0
    return max(
        0.0,
        min(1.0, next_schedule_sigma(current, sigmas) / current),
    )


def temporal_prefix_weights(
    prefix_steps: int = DRIFT_CONTROL_VIDEO_STEPS,
    taper_steps: int = DRIFT_CONTROL_TAPER_STEPS,
) -> tuple[float, ...]:
    count = int(prefix_steps)
    taper = int(taper_steps)
    if count < 1:
        raise ValueError("Drift-Control AV prefix steps must be positive")
    if taper < 1 or taper > count:
        raise ValueError("Drift-Control AV taper steps must fit inside the prefix")
    weights = [1.0] * (count - taper)
    weights.extend(
        float(taper - offset - 1) / float(taper)
        for offset in range(taper)
    )
    return tuple(weights)


def apply_dynamic_prefix_mask(
    packed_mask: torch.Tensor,
    video_shape: tuple[int, ...],
    ratio: float,
    prefix_steps: int = DRIFT_CONTROL_VIDEO_STEPS,
    taper_steps: int = DRIFT_CONTROL_TAPER_STEPS,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Apply the live video-prefix mask used by both sampler and H3."""
    if not torch.is_tensor(packed_mask) or packed_mask.ndim != 3:
        raise ValueError(
            "Drift-Control AV expects a packed denoise mask shaped [B,1,N]"
        )
    shape = tuple(int(value) for value in video_shape)
    if len(shape) != 5 or shape[0] != int(packed_mask.shape[0]):
        raise ValueError(
            f"Drift-Control AV expects video latent [B,C,T,H,W], got {shape}"
        )
    if prefix_steps < 1 or prefix_steps > shape[2]:
        raise ValueError("Drift-Control AV prefix does not fit the target latent")
    video_elements = math.prod(shape[1:])
    if int(packed_mask.shape[-1]) < video_elements:
        raise ValueError("Drift-Control AV packed mask is shorter than its video stream")

    output = packed_mask.clone()
    video_mask = output[..., :video_elements].reshape(shape)
    weights = torch.tensor(
        temporal_prefix_weights(prefix_steps, taper_steps),
        device=video_mask.device,
        dtype=video_mask.dtype,
    ).mul_(float(max(0.0, min(1.0, ratio))))
    video_mask[:, :, :prefix_steps] = weights.view(
        1, 1, prefix_steps, 1, 1
    )
    # Match ComfyUI's H3 token-mask quantization so the sampler blend and the
    # model's per-row timestep labels describe the same live state.
    h3_video_mask = torch.ceil(video_mask[:, :1].float() * 256.0) / 256.0
    return output, h3_video_mask


class _DriftControlMaskState:
    def __init__(self, video_shape: tuple[int, ...], sigmas: Any, prefix_steps: int):
        self.video_shape = tuple(int(value) for value in video_shape)
        self.sigmas = _schedule_values(sigmas)
        self.prefix_steps = int(prefix_steps)
        self.current_video_mask: torch.Tensor | None = None

    def denoise_mask_function(
        self,
        sigma: torch.Tensor,
        denoise_mask: torch.Tensor,
        extra_options: dict[str, Any] | None = None,
    ) -> torch.Tensor:
        current = float(torch.as_tensor(sigma).detach().float().reshape(-1)[0])
        schedule = self.sigmas or _schedule_values(
            (extra_options or {}).get("sigmas", ())
        )
        output, video_mask = apply_dynamic_prefix_mask(
            denoise_mask,
            self.video_shape,
            matched_noise_ratio(current, schedule),
            prefix_steps=self.prefix_steps,
            taper_steps=min(DRIFT_CONTROL_TAPER_STEPS, self.prefix_steps),
        )
        self.current_video_mask = video_mask
        return output

    def apply_model_wrapper(self, executor, *args, **kwargs):
        if self.current_video_mask is not None:
            kwargs["denoise_mask"] = self.current_video_mask
        return executor(*args, **kwargs)


def install_drift_control_av_model(
    model: Any, latent: dict, sigmas: Any, prefix_steps: int,
):
    """Clone an H3 model and install matching sampler/model mask hooks."""
    if model is None or not callable(getattr(model, "clone", None)):
        raise ValueError("Drift-Control AV requires a ComfyUI MODEL input")
    inner = getattr(model, "model", None)
    model_type = str(getattr(getattr(inner, "model_type", None), "name", ""))
    if model_type != "FLOW_AV" and inner.__class__.__name__ != "MiniMaxH3":
        raise ValueError("Drift-Control AV requires a MiniMax H3 AV model")
    samples = latent.get("samples") if isinstance(latent, dict) else None
    if hasattr(samples, "unbind"):
        streams = list(samples.unbind())
    elif hasattr(samples, "tensors"):
        streams = list(samples.tensors)
    elif isinstance(samples, (tuple, list)):
        streams = list(samples)
    else:
        streams = []
    if not streams or not torch.is_tensor(streams[0]) or streams[0].ndim != 5:
        raise ValueError("Drift-Control AV requires a MiniMax H3 AV latent")
    prefix_steps = int(prefix_steps)
    if prefix_steps < 1 or prefix_steps >= int(streams[0].shape[2]):
        raise ValueError("The Drift-Control prefix must fit before newly generated video latent steps")

    patched = model.clone()
    options = getattr(patched, "model_options", None)
    if not isinstance(options, dict):
        raise ValueError("The connected MODEL has no model_options dictionary")
    if callable(options.get("denoise_mask_function")):
        raise ValueError(
            "Drift-Control AV cannot combine with another dynamic denoise-mask patch"
        )
    if not callable(getattr(patched, "set_model_denoise_mask_function", None)):
        raise RuntimeError(
            "Drift-Control AV requires current ComfyUI dynamic denoise-mask support"
        )
    if not callable(getattr(patched, "add_wrapper_with_key", None)):
        raise RuntimeError("Drift-Control AV requires ComfyUI apply-model wrappers")

    from comfy.patcher_extension import WrappersMP

    state = _DriftControlMaskState(tuple(streams[0].shape), sigmas, prefix_steps)
    patched.set_model_denoise_mask_function(state.denoise_mask_function)
    patched.add_wrapper_with_key(
        WrappersMP.APPLY_MODEL,
        _WRAPPER_KEY,
        state.apply_model_wrapper,
    )
    patched.model_options[_WRAPPER_KEY] = state
    return patched
