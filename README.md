# ComfyUI MiniMax H3 Timeline Director

<p align="center">
  <img src="docs/images/creator-wecom.webp" alt="Creator WeCom contact card" width="360">
</p>

<p align="center">
  Creator: <strong>Shi Xiongsong</strong><br>
  <a href="https://space.bilibili.com/219572544?spm_id_from=333.40164.0.0">Bilibili</a>
  ·
  <a href="https://www.youtube.com/@shixiongsong">YouTube</a>
</p>

[简体中文](README_CN.md) · English

An editable reference-media timeline for ComfyUI's native **MiniMax H3 Reference to Video** workflow. It brings reference videos, paired soundtracks, fixed Guides, standalone images, and standalone audio into one compact editing surface.

> Video-generation agents should read the [Chinese segmented long-video guide](docs/AGENT_LONG_VIDEO_GUIDE_CN.md).

## Highlights

- Multi-clip timeline with move, trim, split, delete, snapping, and numeric positioning.
- Only media intersecting the cyan generation range participates in the current reference or Guide plan.
- Three per-clip modes: `Fixed Guide`, `Editable Reference`, and `Boundary Only`.
- Bound source audio follows video edits and can be disabled independently.
- Silent low-resolution monitoring proxies up to `480×270 / 12fps`.
- Multi-select, external file drop, deletion, and drag reordering for image/audio bins.
- Stable `<Picture N>`, `<Video N>`, and `<Audio N>` ordering from UI to H3 inputs.
- Decode-time resizing to the node's `width × height` for VRAM protection.
- Separate merged outputs for timeline soundtracks and standalone reference audio.
- Timeline state is serialized into the ComfyUI workflow JSON.

## Included nodes

| Node | Purpose |
| --- | --- |
| **MiniMax H3 Material Planner** | Edits media and outputs a compact H3 plan plus an ordered Omni media bundle. |
| **MiniMax H3 Omni Media-Bundle Prompt Bridge** | Sends the bundle to an installed Prompt Rewriter Omni backend and returns only `rewritten_prompt`. |
| **MiniMax H3 Plan Encoder** | Combines the plan, prompt, CLIP, and VAEs into H3 conditioning and latent outputs. |
| **MiniMax H3 Timeline Director (Compatibility)** | Preserves the original all-in-one workflow and older saved workflows. |

The split architecture avoids a ComfyUI dependency cycle:

```text
Material Planner ──Omni bundle──> Omni Prompt Bridge ──rewritten_prompt──> Plan Encoder
       └────────────────────H3 plan─────────────────────────────────────> Plan Encoder
```

## Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector.git
```

Restart ComfyUI and search for `MiniMax H3`.

### Requirements

- A recent ComfyUI build with the native MiniMax H3 nodes and `MiniMaxH3AddGuide`.
- MiniMax H3 Ref2VA model, CLIP, video VAE, and audio VAE.
- Python 3.10 or newer.
- ComfyUI's `imageio-ffmpeg` package for low-resolution preview proxies.

No extra pip dependency is declared. The plugin uses PyAV, Pillow, NumPy, PyTorch, torchaudio, aiohttp, and imageio-ffmpeg normally included with a compatible ComfyUI installation.

## Example workflows

### 1. Basic timeline workflow

Uses the compatibility **MiniMax H3 Timeline Director** for direct timeline editing and H3 encoding.

[Download workflow](example_workflows/MiniMax_H3基础时间线规划工作流.json)

![Basic timeline workflow](docs/images/workflow-basic.webp)

### 2. Split planner and encoder

Uses **Material Planner + Plan Encoder** to separate media preparation from H3 encoding.

[Download workflow](example_workflows/MiniMax_H3时间线规划拆分节点工作流.json)

![Split planner and encoder workflow](docs/images/workflow-split.webp)

### 3. Timeline planning with prompt expansion

Adds **MiniMax-H3 Prompt Rewriter Omni (sees and hears)** so the same ordered media can be inspected while producing an H3 prompt.

[Download workflow](example_workflows/MiniMax_H3时间规划+Prompt提示词生成.json)

![Timeline planning and prompt expansion workflow](docs/images/workflow-prompt.webp)

> This workflow requires [MiniMax-H3-Prompt-Rewriter-ComfyUI](https://github.com/pytraveler/MiniMax-H3-Prompt-Rewriter-ComfyUI). Follow that project's instructions for model, quantization, and VRAM requirements.

## Basic usage

1. Set `width`, `height`, and `generation_seconds`.
2. Add video, image, and audio files using the toolbar or direct file drop.
3. Move, trim, or split video clips, then place the cyan range over the interval to generate.
4. Select a purpose for each video:
   - `Fixed Guide` anchors the overlap at its generated-frame positions.
   - `Editable Reference` sends it as `<Video N>` without hard-locking the original subject.
   - `Boundary Only` anchors only the first and last overlap frames.
5. Enable or disable paired video soundtracks as needed.
6. Verify the reference labels at the bottom and run the connected encoder or prompt workflow.

Videos are numbered left-to-right by their intersections with the cyan range. Standalone images and audio follow their visible bin order; drag reordering immediately updates the underlying H3 order.

## Segmented long-video generation

Generate long videos in overlapping segments. Use the previous segment's final shot as the next segment's opening Guide, and describe that overlap as `Shot 1` before new content. When assembling segments, remove the repeated Guide interval from the later segment. See the [Chinese agent guide](docs/AGENT_LONG_VIDEO_GUIDE_CN.md) for the full procedure.

## Credits

- The Omni bridge and prompt-generation workflow reference and adapt [pytraveler/MiniMax-H3-Prompt-Rewriter-ComfyUI](https://github.com/pytraveler/MiniMax-H3-Prompt-Rewriter-ComfyUI).
- See [MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3) for the official model and prompt guidance.
- Thanks to the maintainers of ComfyUI's native MiniMax H3 and Guide nodes.

## License

[GPL-3.0](LICENSE)
