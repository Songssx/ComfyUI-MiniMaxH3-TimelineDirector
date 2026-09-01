# ComfyUI MiniMax H3 Timeline Director

[简体中文](README_CN.md) · English

## Headline feature: lightweight unlimited-length video generation

The plugin splits any target duration into continuous segments and completes them in one ComfyUI
execution: per-segment generation, direct continuation from the previous AV-latent tail, a linear
`0→1` temporal mask, overlap removal, and final synchronized assembly. Extend the result by increasing
the segment count—without generic Loop nodes or duplicated sampler chains. Practical length is limited
only by local VRAM, RAM, disk space, and ComfyUI execution limits.

[Download unlimited-length workflow](example_workflows/MiniMax时间线插件内置有限分段工作流.json) ·
[Chinese guide](docs/FINITE_SEGMENT_EXPANSION_CN.md) ·
[Chinese prompt specification](docs/MiniMax_H3_循环分段提示词_Agent规范.md)

[![Lightweight unlimited-length workflow](https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector/releases/download/v0.6.0/infinite-workflow.webp)](example_workflows/MiniMax时间线插件内置有限分段工作流.json)

### Two directly generated, approximately one-minute examples

Both videos were produced in one plugin execution and are `52.625 seconds / 1263 frames / 24fps`.
Click a poster to play or download the original MP4. All media is hosted as GitHub Release assets, so
it adds nothing to the plugin clone or installation size.

| Finite direct-latent continuation | References with a 48-frame overlap |
| --- | --- |
| [![Play example one](https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector/releases/download/v0.6.0/case-finite-segments-60s.webp)](https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector/releases/download/v0.6.0/H3_finite_segments_60s.mp4) | [![Play example two](https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector/releases/download/v0.6.0/case-reference-overlap-60s.webp)](https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector/releases/download/v0.6.0/H3_reference_overlap48_60s.mp4) |

<p align="center">
  <img src="docs/images/creator-wecom.webp" alt="Creator WeCom contact card" width="360">
</p>

<p align="center">
  Creator: <strong>Shi Xiongsong</strong><br>
  <a href="https://space.bilibili.com/219572544?spm_id_from=333.40164.0.0">Bilibili</a>
  ·
  <a href="https://www.youtube.com/@shixiongsong">YouTube</a>
</p>

An editable reference-media timeline for ComfyUI's native **MiniMax H3 Reference to Video** workflow. It brings reference videos, paired soundtracks, fixed Guides, standalone images, and standalone audio into one compact editing surface.

> Video-generation agents should read the [Chinese segmented long-video guide](docs/AGENT_LONG_VIDEO_GUIDE_CN.md).

## Highlights

- Multi-clip timeline with move, trim, split, delete, snapping, and numeric positioning.
- Only media intersecting the cyan generation range participates in the current reference or Guide plan.
- Three per-clip modes: `Fixed Guide`, `Editable Reference`, and `Boundary Only`.
- Native text-to-video when no image, video, or audio material is uploaded; the encoder creates the standard empty H3 AV latent from the prompt alone.
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
| **MiniMax H3 Finite Segment Expansion** | Creates a lightweight long-video plan from prompt/material ordinals without sampling. |
| **MiniMax H3 Finite Segment Sampling** | Expands an acyclic graph for direct-latent continuation, masking, sampling, deduplication, and assembly. |
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

- A recent ComfyUI build with the native MiniMax H3 nodes; `MiniMaxH3AddGuide` is additionally required only when Guides are used.
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

### 4. Plugin-owned unlimited-length video generation

**MiniMax H3 Finite Segment Expansion** only validates prompts, segment count, and media
assignments; it performs no sampling. Connect its plan to **MiniMax H3 Finite Segment Sampling**
to build a standard acyclic graph for direct AV-latent continuation, linear temporal masking,
overlap removal, and ordered assembly. No generic Loop nodes are required.

[Download finite workflow](example_workflows/MiniMax时间线插件内置有限分段工作流.json) ·
[Chinese guide](docs/FINITE_SEGMENT_EXPANSION_CN.md) ·
[Chinese prompt specification](docs/MiniMax_H3_循环分段提示词_Agent规范.md)

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

### Finite direct-latent continuation

Finite sampling carries the previous sampled AV latent tail directly into the next opening,
avoids an RGB decode/re-encode round trip, and applies a `0→1` temporal noise ramp across the
overlap. The old generic-loop helper nodes and PR #15923 dependency have been removed.

## Credits

- The Omni bridge and prompt-generation workflow reference and adapt [pytraveler/MiniMax-H3-Prompt-Rewriter-ComfyUI](https://github.com/pytraveler/MiniMax-H3-Prompt-Rewriter-ComfyUI).
- See [MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3) for the official model and prompt guidance.
- Thanks to the maintainers of ComfyUI's native MiniMax H3 and Guide nodes.

## License

[GPL-3.0](LICENSE)
