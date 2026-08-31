"""Submit a three-segment MiniMax H3 direct-latent loop to ComfyUI.

Requires the generic Loop implementation from ComfyUI PR #15923 and this
plugin's MiniMaxH3Loop* helper nodes.  The output is accumulated incrementally,
so decoded segments do not all remain in memory.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


SEGMENT_PROMPTS = [
    """integrated_multimodal_description:
[Shot 1] A single continuous medium shot in a softly lit modern studio. A young woman with short black hair, wearing a matte teal jacket over a cream shirt, stands beside a wooden desk. She slowly turns toward the camera, lifts a small blue glass sphere with both hands, and smiles subtly. The camera makes a very slow forward dolly. Soft daylight enters from frame left; neutral white balance, natural skin tones, restrained teal and warm wood colors, moderate contrast, and realistic texture. No cut, no transition, and no sudden lighting change.
overall_soundscape:
Quiet indoor room tone with subtle cloth movement and a faint glass touch.
non_diegetic_music:
N/A""",
    """integrated_multimodal_description:
[Shot 1] In the same uninterrupted studio shot, the same woman gently rotates the blue glass sphere and looks down at its reflection. A soft blue glow travels once through the glass, illuminating her fingertips without changing the room exposure. She then looks back toward the camera. Continue the same slow forward dolly, character position, set geometry, lighting direction, neutral white balance, restrained saturation, and realistic texture. No cut or transition.
overall_soundscape:
The same quiet indoor room tone continues, with subtle cloth movement and a delicate glass resonance.
non_diegetic_music:
N/A""",
    """integrated_multimodal_description:
[Shot 1] The same continuous studio shot carries on. The woman lowers the softly glowing blue glass sphere toward the wooden desk, pauses just above its surface, and gives a calm confirming nod. The camera eases to a stop while preserving the established framing, character position, environment, lighting, neutral white balance, restrained teal and warm wood palette, and natural skin tones. No cut or transition.
overall_soundscape:
The same quiet room tone continues; a soft wooden contact sound closes the action.
non_diegetic_music:
N/A""",
]


def workflow(iterations: int = 3, overlap_frames: int = 22) -> dict:
    p = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_ref2va_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "minimax_h3\\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "5": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": "minimax_h3_fl2v_lightx2v_turbo_4step_v1.0_768p_resized_avg_rank_31_bf16.safetensors", "strength_model": 1.0}},
        "6": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "7": {"class_type": "BasicScheduler", "inputs": {"model": ["5", 0], "scheduler": "simple", "steps": 8, "denoise": 1.0}},
        "10": {"class_type": "Loop", "inputs": {"mode": "simple", "mode.num_iterations": iterations}},
        "11": {"class_type": "LoopVariable", "inputs": {"next_value": ["24", 0], "iteration": ["10", 0]}},
        "12": {"class_type": "MiniMaxH3LoopPromptSelector", "inputs": {"iteration": ["10", 0], "segment_prompts": json.dumps(SEGMENT_PROMPTS, ensure_ascii=False), "overlap_frames": overlap_frames, "inject_continuity_instruction": True}},
        "13": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"clip": ["2", 0], "vae": ["3", 0], "prompt": ["12", 0], "width": 640, "height": 352, "length": 124}},
        "14": {"class_type": "MiniMaxH3LoopLatentGuide", "inputs": {"positive": ["13", 0], "target_latent": ["13", 1], "is_first": ["10", 1], "iteration": ["10", 0], "previous_latent": ["11", 0], "overlap_frames": overlap_frames, "continue_audio_latent": True}},
        "15": {"class_type": "RandomNoise", "inputs": {"noise_seed": 2608284242}},
        "16": {"class_type": "BasicGuider", "inputs": {"model": ["5", 0], "conditioning": ["14", 0]}},
        "17": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["15", 0], "guider": ["16", 0], "sampler": ["6", 0], "sigmas": ["7", 0], "latent_image": ["14", 1]}},
        "18": {"class_type": "VAEDecode", "inputs": {"samples": ["17", 0], "vae": ["3", 0]}},
        "19": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["17", 0], "vae": ["4", 0]}},
        "24": {"class_type": "MiniMaxH3LoopSegmentFinalize", "inputs": {"sampled_latent": ["17", 0], "images": ["18", 0], "audio": ["19", 0], "iteration": ["10", 0], "overlap_frames": overlap_frames}},
        "25": {"class_type": "CreateVideo", "inputs": {"images": ["24", 1], "audio": ["24", 2], "fps": 24.0, "bit_depth": 8, "color_space": "sRGB"}},
        "26": {"class_type": "AccumulateSaveVideo", "inputs": {"video": ["25", 0], "filename_prefix": "video/H3_latent_loop/three_segment_direct_latent", "format": "mp4", "codec": "h264", "last": ["10", 2]}},
    }
    return {"prompt": p, "client_id": f"h3-latent-loop-{uuid.uuid4()}"}


def request_json(url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://127.0.0.1:8891")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--overlap-frames", type=int, default=22)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--write-api-json", type=Path)
    args = parser.parse_args()

    payload = workflow(args.iterations, args.overlap_frames)
    if args.write_api_json:
        args.write_api_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    submitted = request_json(f"{args.server}/prompt", payload)
    prompt_id = submitted["prompt_id"]
    print(f"submitted: {prompt_id}", flush=True)
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        history = request_json(f"{args.server}/history/{prompt_id}")
        if prompt_id in history:
            record = history[prompt_id]
            status = record.get("status", {})
            print(json.dumps(record, ensure_ascii=False, indent=2))
            if status.get("status_str") != "success":
                raise RuntimeError(f"workflow failed: {status}")
            return
        time.sleep(3)
    raise TimeoutError(f"workflow did not finish within {args.timeout}s: {prompt_id}")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"))
        raise
