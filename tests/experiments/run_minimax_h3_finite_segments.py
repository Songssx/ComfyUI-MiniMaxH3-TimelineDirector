"""Submit a small plugin-owned finite-expansion H3 workflow to ComfyUI."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid


PROMPTS = [
    """subject_definitions:
<Subject 1> is the adventurer in <Picture 1>, preserving the reference identity and costume.
summary:
[reference generation] The adventurer turns toward a softly glowing blue crystal.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and clothing follow <Picture 1>.
detailed_description:
[Shot 1] A stable medium shot. The adventurer turns toward a softly glowing blue crystal and slowly raises one hand. The final second settles into a clear still composition.
overall_soundscape:
Quiet room tone and a soft crystal resonance.
non_diegetic_music:
N/A""",
    """subject_definitions:
<Subject 1> is the same adventurer carried into the opening Latent Guide; <Picture 1> calibrates the established identity and costume.
summary:
[video continuation + reference generation] The crystal response continues without a cut.
retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - the opening Latent Guide preserves pose and <Picture 1> calibrates identity.
detailed_description:
[Shot 1] The same stable composition continues. After the fixed opening, the adventurer gently closes one hand around the blue crystal and gives a calm nod.
overall_soundscape:
The same quiet room tone and crystal resonance continue.
non_diegetic_music:
N/A""",
]


def payload(image_file: str, steps: int) -> dict:
    timeline = {
        "version": 4,
        "fps": 24,
        "selection": {"start": 0, "duration": 2.34},
        "videoAudioEnabled": True,
        "videoClips": [],
        "images": [{"id": "p1", "file": image_file, "name": image_file}],
        "audios": [],
        "segmentConfig": {"count": 0, "segments": []},
    }
    prompt = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_ref2va_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "minimax_h3\\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "5": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": "minimax_h3_fl2v_lightx2v_turbo_4step_v1.0_768p_resized_avg_rank_31_bf16.safetensors", "strength_model": 1.0}},
        "6": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "7": {"class_type": "BasicScheduler", "inputs": {"model": ["5", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "8": {"class_type": "MiniMaxH3TimelinePlanner", "inputs": {"width": 512, "height": 288, "generation_seconds": 2.34, "timeline_data": json.dumps(timeline, ensure_ascii=False)}},
        "9": {"class_type": "MiniMaxH3FiniteSegmentExpansion", "inputs": {"plan": ["8", 0], "segment_prompts": json.dumps(PROMPTS, ensure_ascii=False), "segment_count": 2, "overlap_frames": 22, "inject_continuity_instruction": True}},
        "12": {"class_type": "MiniMaxH3FiniteSegmentSampler", "inputs": {"model": ["5", 0], "clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0], "finite_plan": ["9", 0], "sampler": ["6", 0], "sigmas": ["7", 0], "seed": 2608310001, "continue_audio_latent": True, "ref_image_size": "match"}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["12", 1], "audio": ["12", 2], "fps": 24.0, "bit_depth": 8, "color_space": "sRGB"}},
        "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": "video/H3_finite_segments/two_segment_smoke", "format": "mp4", "codec": "h264"}},
    }
    return {"prompt": prompt, "client_id": f"h3-finite-{uuid.uuid4()}"}


def request_json(url: str, data=None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--image-file", default="minimax_h3_timeline_director/1787906969288_g2y0a_Krea2_turbo_00032_.png")
    args = parser.parse_args()
    submitted = request_json(f"{args.server}/prompt", payload(args.image_file, args.steps))
    prompt_id = submitted["prompt_id"]
    print(f"submitted: {prompt_id}", flush=True)
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        history = request_json(f"{args.server}/history/{prompt_id}")
        if prompt_id in history:
            record = history[prompt_id]
            print(json.dumps(record, ensure_ascii=False, indent=2))
            if record.get("status", {}).get("status_str") != "success":
                raise RuntimeError(record.get("status"))
            return
        time.sleep(3)
    raise TimeoutError(prompt_id)


if __name__ == "__main__":
    main()
