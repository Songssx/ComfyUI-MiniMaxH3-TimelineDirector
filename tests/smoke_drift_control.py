"""Focused smoke test for experimental Drift-Control AV mask math."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import torch
from aiohttp import web
from server import PromptServer


class _FlowAV:
    name = "FLOW_AV"


class _MiniMaxModel:
    model_type = _FlowAV()


class _FakeModelPatcher:
    def __init__(self):
        self.model = _MiniMaxModel()
        self.model_options = {}
        self.mask_function = None
        self.wrappers = {}

    def clone(self):
        return _FakeModelPatcher()

    def set_model_denoise_mask_function(self, function):
        self.mask_function = function
        self.model_options["denoise_mask_function"] = function

    def add_wrapper_with_key(self, wrapper_type, key, wrapper):
        self.wrappers[(wrapper_type, key)] = wrapper


def _load_module(plugin_dir: Path):
    if not hasattr(PromptServer, "instance"):
        PromptServer.instance = types.SimpleNamespace(routes=web.RouteTableDef())
    package_name = "minimax_h3_drift_control_smoke"
    spec = importlib.util.spec_from_file_location(
        package_name, plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.drift_control_av"]


def main():
    drift = _load_module(Path(__file__).resolve().parents[1])
    schedule = torch.tensor([1.0, 0.8, 0.5, 0.2, 0.0])
    assert drift.drift_control_step_count(schedule) == 4
    assert abs(drift.next_schedule_sigma(0.8, schedule) - 0.5) < 1e-6
    assert abs(drift.matched_noise_ratio(0.8, schedule) - 0.625) < 1e-6
    assert drift.temporal_prefix_weights() == (
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
        0.75, 0.5, 0.25, 0.0,
    )

    # The packed tail represents audio. It must remain exactly unchanged.
    video_shape = (1, 2, 15, 2, 2)
    video_elements = 1 * 2 * 15 * 2 * 2
    packed = torch.ones((1, 1, video_elements + 17), dtype=torch.float32)
    output, h3_mask = drift.apply_dynamic_prefix_mask(
        packed, video_shape, ratio=0.5,
    )
    video = output[..., :video_elements].reshape(video_shape)
    expected = torch.tensor(
        [0.5] * 8 + [0.375, 0.25, 0.125, 0.0], dtype=torch.float32
    )
    assert torch.allclose(video[0, 0, :12, 0, 0], expected)
    assert torch.all(video[:, :, 12:] == 1)
    assert torch.equal(output[..., video_elements:], packed[..., video_elements:])
    assert h3_mask.shape == (1, 1, 15, 2, 2)
    assert torch.equal(h3_mask, torch.ceil(video[:, :1] * 256.0) / 256.0)

    short_output, _ = drift.apply_dynamic_prefix_mask(
        packed, video_shape, ratio=0.5, prefix_steps=7, taper_steps=4,
    )
    short_video = short_output[..., :video_elements].reshape(video_shape)
    short_expected = torch.tensor(
        [0.5] * 3 + [0.375, 0.25, 0.125, 0.0], dtype=torch.float32
    )
    assert torch.allclose(short_video[0, 0, :7, 0, 0], short_expected)
    assert torch.all(short_video[:, :, 7:] == 1)

    latent = {
        "samples": (
            torch.zeros(video_shape, dtype=torch.float32),
            torch.zeros((1, 2, 2, 8), dtype=torch.float32),
        )
    }
    patched = drift.install_drift_control_av_model(
        _FakeModelPatcher(), latent, schedule, prefix_steps=7,
    )
    assert patched.mask_function is not None
    state = patched.model_options["minimax_h3_timeline_drift_control_av"]
    live = patched.mask_function(torch.tensor([0.8]), packed, {"sigmas": schedule})
    live_video = live[..., :video_elements].reshape(video_shape)
    assert abs(live_video[0, 0, 0, 0, 0].item() - 0.625) < 1e-6
    captured = {}

    def executor(*args, **kwargs):
        captured.update(kwargs)
        return "ok"

    assert state.apply_model_wrapper(executor, input="x") == "ok"
    assert torch.equal(captured["denoise_mask"], state.current_video_mask)
    print("drift control AV smoke test: PASS")


if __name__ == "__main__":
    main()
