"""Learned latent-space lifter for MiniMax H3 (3D-conv upscaler).

Bundles the inference architecture of the Minimax H3 Latent Upscaler
(LBH-123-AI/Minimax_h3_latent_Upscaler, architecture drawing on the LTX 2.3
spatial upscaler) as an optional experimental replacement for SelfLift-zero's
nearest-neighbor latent lift. This external model is not the SelfLift-rich
lifter described by the paper. The checkpoint is expected under
ComfyUI/models/latent_upscale_models/.
"""

import logging
import os

import torch
import torch.nn as nn
import torch.nn.functional as F

import comfy.model_management
import comfy.model_patcher
import folder_paths

from comfy.ldm.minimax.vae import LATENTS_MEAN, LATENTS_STD

from .diagnostics import log_memory

_FOLDER = "latent_upscale_models"

if _FOLDER not in folder_paths.folder_names_and_paths:
    folder_paths.add_model_folder_path(_FOLDER, os.path.join(folder_paths.models_dir, _FOLDER))


def _normalization(channels):
    return nn.GroupNorm(32, channels)


def _zero_module(module):
    for p in module.parameters():
        p.detach().zero_()
    return module


def _temporal_windows(length, chunk, overlap):
    for start in range(0, length, chunk):
        end = min(length, start + chunk)
        yield start, end, max(0, start - overlap), min(length, end + overlap)


class AttnBlock3D(nn.Module):
    def __init__(self, in_channels):
        super().__init__()
        self.norm = _normalization(in_channels)
        self.q = nn.Conv3d(in_channels, in_channels, 1)
        self.k = nn.Conv3d(in_channels, in_channels, 1)
        self.v = nn.Conv3d(in_channels, in_channels, 1)
        self.proj_out = nn.Conv3d(in_channels, in_channels, 1)

    def forward(self, x):
        h = self.norm(x)
        q = self.q(h).flatten(2).movedim(-1, 1).unsqueeze(1)
        k = self.k(h).flatten(2).movedim(-1, 1).unsqueeze(1)
        v = self.v(h).flatten(2).movedim(-1, 1).unsqueeze(1)
        h = F.scaled_dot_product_attention(q, k, v)
        h = h.squeeze(1).movedim(1, -1).reshape(x.shape)
        return x + self.proj_out(h)


class ResBlockEmb3D(nn.Module):
    def __init__(self, channels, emb_channels, dropout=0, out_channels=None):
        super().__init__()
        self.out_channels = out_channels or channels
        self.in_layers = nn.Sequential(
            _normalization(channels), nn.SiLU(),
            nn.Conv3d(channels, self.out_channels, 3, padding=1),
        )
        self.emb_layers = nn.Sequential(
            nn.SiLU(), nn.Linear(emb_channels, 2 * self.out_channels),
        )
        self.out_norm = _normalization(self.out_channels)
        self.out_layers = nn.Sequential(
            nn.SiLU(), nn.Dropout(p=dropout),
            _zero_module(nn.Conv3d(self.out_channels, self.out_channels, 3, padding=1)),
        )
        self.skip = (
            nn.Conv3d(channels, self.out_channels, 1)
            if self.out_channels != channels else nn.Identity()
        )

    def forward(self, x, emb):
        h = self.in_layers(x)
        emb_out = self.emb_layers(emb).type(h.dtype)
        while len(emb_out.shape) < len(h.shape):
            emb_out = emb_out[..., None]
        scale, shift = torch.chunk(emb_out, 2, dim=1)
        h = self.out_norm(h) * (1 + scale) + shift
        h = self.out_layers(h)
        return self.skip(x) + h


class TemporalConv(nn.Module):
    def __init__(self, channels, kernel_size=5):
        super().__init__()
        padding = kernel_size // 2
        self.norm = _normalization(channels)
        self.dwconv = nn.Conv3d(channels, channels,
                                kernel_size=(kernel_size, 1, 1),
                                padding=(padding, 0, 0),
                                groups=channels)
        self.pwconv = nn.Conv3d(channels, channels, kernel_size=1)
        nn.init.zeros_(self.pwconv.weight)
        nn.init.zeros_(self.pwconv.bias)

    def forward(self, x):
        identity = x
        h = self.norm(x)
        h = F.silu(h)
        h = self.dwconv(h)
        h = self.pwconv(h)
        return identity + h


class LatentResizer3D(nn.Module):
    """Pure-3D upscaler backbone with optional temporal chunking (LBH-123-AI architecture)."""

    def __init__(self, in_channels=24, in_blocks=12, out_blocks=12,
                 channels=512, dropout=0.1, attn=False,
                 temporal_every=2, temporal_kernel=5):
        super().__init__()
        self.conv_in = nn.Conv3d(in_channels, channels, 3, padding=1)
        embed_dim = 64
        self.embed = nn.Sequential(
            nn.Linear(1, embed_dim), nn.SiLU(), nn.Linear(embed_dim, embed_dim))

        self.in_blocks = nn.ModuleList()
        for b in range(in_blocks):
            if (b == 1 or b == in_blocks - 1) and attn:
                self.in_blocks.append(AttnBlock3D(channels))
            self.in_blocks.append(ResBlockEmb3D(channels, embed_dim, dropout))
            if temporal_every > 0 and b % temporal_every == 0:
                self.in_blocks.append(TemporalConv(channels, temporal_kernel))

        self.out_blocks = nn.ModuleList()
        for b in range(out_blocks):
            if (b == 1 or b == out_blocks - 1) and attn:
                self.out_blocks.append(AttnBlock3D(channels))
            self.out_blocks.append(ResBlockEmb3D(channels, embed_dim, dropout))
            if temporal_every > 0 and b % temporal_every == 0:
                self.out_blocks.append(TemporalConv(channels, temporal_kernel))

        self.norm_out = _normalization(channels)
        self.conv_out = nn.Conv3d(channels, in_channels, 3, padding=1)

    def temporal_chunk_settings(self):
        for block in self.in_blocks:
            if isinstance(block, TemporalConv):
                return 32, block.dwconv.weight.shape[2]
        return 32, 0

    def temporal_receptive_radius(self):
        """Return the exact finite temporal-convolution radius of the network.

        Continuation lifting can evaluate the disposable prefix and retained
        suffix independently.  Each side therefore needs a halo covering every
        stacked temporal convolution, not merely one temporal kernel; otherwise
        zero-padding from the artificial split reaches the first retained H3
        token and decodes as a dark/bright flash at the timeline seam.
        """
        radius = int(self.conv_in.kernel_size[0]) // 2
        for block in (*self.in_blocks, *self.out_blocks):
            if isinstance(block, TemporalConv):
                radius += int(block.dwconv.kernel_size[0]) // 2
        radius += int(self.conv_out.kernel_size[0]) // 2
        return radius

    def temporal_window_budget(self, length):
        chunk, overlap = self.temporal_chunk_settings()
        return length if length <= chunk else min(length + 2 * overlap, chunk + 4 * overlap)

    def forward(self, x, scale=None, target_size=None, enable_chunking=True):
        if target_size is not None:
            size = target_size
        elif scale is not None:
            size = tuple(int(round(s * scale)) for s in x.shape[-3:])
        else:
            return x

        if size == x.shape[-3:]:
            return x

        B, C, T, H, W = x.shape

        chunk, overlap = self.temporal_chunk_settings()

        if not enable_chunking or T <= chunk:
            return self._forward_seg(x, scale, size)

        x_padded = F.pad(x, (0, 0, 0, 0, overlap, overlap), mode='replicate')

        out_full = torch.zeros(B, C, T, size[-2], size[-1], device=x.device, dtype=x.dtype)
        weight_full = torch.zeros(1, 1, T, 1, 1, device=x.device, dtype=x.dtype)

        for seg_start, seg_end, out_start, out_end in _temporal_windows(T, chunk, overlap):
            lo = out_start
            hi = out_end + 2 * overlap

            seg = x_padded[:, :, lo:hi].contiguous()
            seg_size = (hi - lo, size[-2], size[-1])
            seg_out = self._forward_seg(seg, scale, seg_size)

            s0 = (out_start + overlap) - lo
            s1 = s0 + (out_end - out_start)
            valid_out = seg_out[:, :, s0:s1]
            n_valid = out_end - out_start

            weight = torch.ones(n_valid, device=x.device, dtype=x.dtype)
            if seg_start > out_start:
                blend_len = seg_start - out_start
                weight[:blend_len] = torch.arange(1, blend_len + 1, device=x.device, dtype=x.dtype) / (blend_len + 1)
            if out_end > seg_end:
                blend_len = out_end - seg_end
                weight[-blend_len:] = torch.arange(blend_len, 0, -1, device=x.device, dtype=x.dtype) / (blend_len + 1)

            out_full[:, :, out_start:out_end] += valid_out * weight.view(1, 1, n_valid, 1, 1)
            weight_full[:, :, out_start:out_end] += weight.view(1, 1, n_valid, 1, 1)

            del seg, seg_out, valid_out

        return out_full / weight_full.clamp(min=1e-8)

    def _forward_seg(self, x, scale, size):
        scale_emb = torch.tensor(
            [scale - 1 if scale is not None else 0.0],
            dtype=x.dtype, device=x.device).unsqueeze(0)
        emb = self.embed(scale_emb)

        x = self.conv_in(x)
        for b in self.in_blocks:
            if isinstance(b, ResBlockEmb3D):
                x = b(x, emb.expand(x.shape[0], -1))
            else:
                x = b(x)

        x = F.interpolate(x, size=size, mode="trilinear", align_corners=False)

        for b in self.out_blocks:
            if isinstance(b, ResBlockEmb3D):
                x = b(x, emb.expand(x.shape[0], -1))
            else:
                x = b(x)

        x = self.norm_out(x)
        x = F.silu(x)
        return self.conv_out(x)


_model_cache = {}


def _model_path(model_name):
    for folder in folder_paths.get_folder_paths(_FOLDER):
        candidate = os.path.join(folder, model_name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _canonical_weight_key(name):
    key = str(name)
    prefixes = ("state_dict.", "module.", "model.", "upscaler.")
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if key.startswith(prefix):
                key = key[len(prefix):]
                changed = True
                break
    return key


def checkpoint_is_h3_compatible(model_name):
    """Cheaply reject unrelated safetensors without loading their tensors."""

    path = _model_path(model_name)
    if path is None:
        return False
    if os.path.splitext(path)[1].lower() != ".safetensors":
        # PyTorch checkpoints have no cheap header-only key reader. Let the
        # regular loader validate these less common files.
        return "h3" in str(model_name).lower() or "minimax" in str(model_name).lower()
    try:
        from safetensors import safe_open
        with safe_open(path, framework="pt", device="cpu") as checkpoint:
            return any(_canonical_weight_key(key) == "conv_in.weight" for key in checkpoint.keys())
    except Exception:
        return False


def list_upscaler_models():
    try:
        paths = folder_paths.get_folder_paths(_FOLDER)
    except KeyError:
        return []
    names = []
    for p in paths:
        for root, _, files in os.walk(p):
            for f in files:
                if os.path.splitext(f)[1].lower() in (".pth", ".safetensors"):
                    names.append(os.path.relpath(os.path.join(root, f), p))
    # Keep every file visible, matching ComfyUI's model-directory behavior,
    # while putting checkpoints that implement the H3 3D latent-lifter
    # architecture first so an empty/new planner never defaults to an LTX model.
    return sorted(set(names), key=lambda name: (not checkpoint_is_h3_compatible(name), name.lower()))


def _detect_arch(sd):
    import re
    cfg = {"in_channels": 24, "in_blocks": 12, "out_blocks": 12, "channels": 512,
           "dropout": 0.1, "attn": False, "temporal_every": 2, "temporal_kernel": 5}
    if 'conv_in.weight' in sd:
        cfg["in_channels"] = sd['conv_in.weight'].shape[1]
        cfg["channels"] = sd['conv_in.weight'].shape[0]
    in_ids, out_ids, tin, tout = set(), set(), set(), set()
    for k in sd:
        m = re.match(r'in_blocks\.(\d+)\.in_layers\.', k)
        if m: in_ids.add(int(m.group(1)))
        m = re.match(r'out_blocks\.(\d+)\.in_layers\.', k)
        if m: out_ids.add(int(m.group(1)))
        m = re.match(r'in_blocks\.(\d+)\.dwconv\.weight', k)
        if m: tin.add(int(m.group(1)))
        m = re.match(r'out_blocks\.(\d+)\.dwconv\.weight', k)
        if m: tout.add(int(m.group(1)))
    if in_ids: cfg["in_blocks"] = len(in_ids)
    if out_ids: cfg["out_blocks"] = len(out_ids)
    if tin or tout:
        cfg["temporal_every"] = 2
        for k in sd:
            if k.endswith('dwconv.weight'):
                cfg["temporal_kernel"] = sd[k].shape[2]
                break
    else:
        cfg["temporal_every"] = 0
    cfg["attn"] = False
    return cfg


def _normalize_checkpoint_keys(state_dict):
    if not isinstance(state_dict, dict):
        raise ValueError("SelfLift: latent upscaler checkpoint is not a state dictionary")
    normalized = {_canonical_weight_key(name): value for name, value in state_dict.items()}
    return normalized


def _normalize_checkpoint_dtype(state_dict, model_name=""):
    weight = state_dict.get("conv_in.weight")
    if weight is None:
        label = f" '{model_name}'" if model_name else ""
        raise ValueError(
            f"SelfLift: selected latent upscaler{label} is not compatible with MiniMax H3 "
            "(missing conv_in.weight). Select minimax_h3_latent_upscaler_3d_bf16.safetensors; "
            "LTX spatial/temporal upscalers cannot be used for H3 two-stage sampling."
        )
    dtype = weight.dtype
    if str(dtype).startswith("torch.float8_"):
        dtype = torch.bfloat16 if any(value.dtype == torch.bfloat16 for value in state_dict.values()) else torch.float16
    if dtype not in (torch.float16, torch.bfloat16, torch.float32, torch.float64):
        raise ValueError(f"SelfLift: unsupported upscaler weight dtype {dtype}")
    if any(value.is_floating_point() and value.dtype != dtype for value in state_dict.values()):
        logging.debug("TimelineDirector: normalizing mixed upscaler floating-point tensors to %s", dtype)
    return {name: value.to(dtype=dtype) if value.is_floating_point() else value
            for name, value in state_dict.items()}


def _load_model(model_name, device):
    key = (model_name, str(device))
    if key in _model_cache:
        return _model_cache[key]

    path = _model_path(model_name)
    if path is None:
        raise FileNotFoundError(f"latent upscaler model not found: {model_name} (place it under ComfyUI/models/{_FOLDER}/)")

    import comfy.utils
    sd = comfy.utils.load_torch_file(path)
    if isinstance(sd, dict) and 'model' in sd:
        sd = sd['model']
    sd = _normalize_checkpoint_keys(sd)
    sd = _normalize_checkpoint_dtype(sd, model_name)

    cfg = _detect_arch(sd)
    with torch.device("meta"):
        model = LatentResizer3D(
            in_channels=cfg["in_channels"], in_blocks=cfg["in_blocks"], out_blocks=cfg["out_blocks"],
            channels=cfg["channels"], dropout=cfg["dropout"], attn=cfg["attn"],
            temporal_every=cfg["temporal_every"], temporal_kernel=cfg["temporal_kernel"],
        )
    model.load_state_dict(sd, strict=True, assign=True)
    model = model.eval().requires_grad_(False)
    patcher = comfy.model_patcher.CoreModelPatcher(
        model, load_device=device,
        offload_device=comfy.model_management.unet_offload_device())
    _model_cache[key] = patcher
    return patcher


def _inference_memory_required(model, z0_low, out_hw):
    H, W = out_hw
    T = z0_low.shape[2]
    temporal_window = model.temporal_window_budget(T)
    feature_elements = z0_low.shape[0] * model.conv_in.out_channels * temporal_window * H * W
    return feature_elements * model.conv_in.weight.element_size() * 8


def learned_latent_lift(z0_low, out_hw, model_name, device=None, temporal_split=None):
    """2D/3D learned upsample of the low-res clean endpoint to the target latent size.

    z0_low: [B, 24, T, h, w] H3 video latent in VAE space. Returns [B, 24, T, H, W].
    """
    H, W = out_hw
    if device is None:
        device = comfy.model_management.get_torch_device()
    h, w = z0_low.shape[-2], z0_low.shape[-1]
    scale = (H / h + W / w) / 2.0

    log_memory("upscaler before_load", device)
    patcher = _load_model(model_name, device)
    model = patcher.model
    memory_required = _inference_memory_required(model, z0_low, (H, W))
    length = z0_low.shape[2]
    chunk, overlap = model.temporal_chunk_settings()
    identity = (H, W) == (h, w)
    chunked = not identity and length > chunk
    windows = list(_temporal_windows(length, chunk, overlap)) if chunked else []
    actual_window = max(end - start + 2 * overlap for _, _, start, end in windows) if chunked else length
    budget_window = model.temporal_window_budget(length)
    logging.debug("[TimelineDirector upscaler] model=%s dtype=%s input=%s target_hw=%s "
                 "spatial_lift=(%.4f, %.4f) scale_embedding=%.4f mode=%s "
                 "chunk=%d overlap=%d windows=%d max_input_window=%d budget_window=%d "
                 "estimated_workspace=%.2f MiB",
                 model_name, model.conv_in.weight.dtype, tuple(z0_low.shape), (H, W),
                 H / h, W / w, scale - 1.0, "identity" if identity else "chunked" if chunked else "full",
                 chunk, overlap if chunked else 0, len(windows) if chunked else int(not identity),
                 actual_window if not identity else 0, budget_window, memory_required / 2**20)
    comfy.model_management.load_models_gpu([patcher], memory_required=memory_required)
    log_memory("upscaler after_load", device)
    dtype = model.conv_in.weight.dtype
    mean = torch.tensor(LATENTS_MEAN, dtype=dtype, device=device).view(1, -1, 1, 1, 1)
    std = torch.tensor(LATENTS_STD, dtype=dtype, device=device).view(1, -1, 1, 1, 1)

    x = z0_low.to(device=device, dtype=dtype)
    with torch.no_grad():
        x = (x - mean) / std
        split = int(temporal_split or 0)
        if 0 < split < int(x.shape[2]):
            # A continuation prefix and its newly generated suffix carry
            # different ownership. Lift the disposable prefix independently,
            # but let the retained suffix see the real low-resolution prefix as
            # read-only left context. Repeating the suffix's first token for the
            # whole halo makes the 3D model treat it as a fresh video opening and
            # produces a deterministic dark/bright pulse after overlap trimming.
            halo = max(2, int(model.temporal_receptive_radius()))

            prefix = x[:, :, :split]
            prefix_length = int(prefix.shape[2])
            padded_prefix = F.pad(
                prefix, (0, 0, 0, 0, halo, halo), mode="replicate"
            )
            lifted_prefix = model(
                padded_prefix, scale=scale,
                target_size=(prefix_length + 2 * halo, H, W),
            )[:, :, halo:halo + prefix_length]

            suffix = x[:, :, split:]
            suffix_length = int(suffix.shape[2])
            left_context = x[:, :, max(0, split - halo):split]
            if int(left_context.shape[2]) < halo:
                left_context = F.pad(
                    left_context,
                    (0, 0, 0, 0, halo - int(left_context.shape[2]), 0),
                    mode="replicate",
                )
            right_context = suffix[:, :, -1:].expand(-1, -1, halo, -1, -1)
            padded_suffix = torch.cat((left_context, suffix, right_context), dim=2)
            lifted_suffix = model(
                padded_suffix, scale=scale,
                target_size=(suffix_length + 2 * halo, H, W),
            )[:, :, halo:halo + suffix_length]
            out = torch.cat((lifted_prefix, lifted_suffix), dim=2)
            logging.debug(
                "[SelfLift upscaler] continuation boundary at token=%d uses "
                "a real low-resolution left-context halo=%d",
                split, halo,
            )
            del (
                prefix, padded_prefix, lifted_prefix, suffix, left_context,
                right_context, padded_suffix, lifted_suffix,
            )
        else:
            out = model(x, scale=scale, target_size=(z0_low.shape[2], H, W))
        out = (out * std + mean).float().to(comfy.model_management.intermediate_device())
    log_memory("upscaler end", device)
    return out
