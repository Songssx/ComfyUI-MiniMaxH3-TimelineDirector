# ComfyUI MiniMax H3 Timeline Director

Start with the [**MiniMaxH3 All-in-One Full Timeline Director workflow**](example_workflows/MiniMaxH3全功能合一完全体导演台工作流.json):
one lightweight graph covers text-to-video, image reference, audio-driven generation, video editing,
character replacement, motion transfer, digital humans, and manually segmented long-video generation.

[简体中文](README_CN.md) · English

## Headline feature: lightweight unlimited-length video generation

The plugin splits any target duration into continuous segments and completes them in one ComfyUI
execution: per-segment generation with one shared seed, direct continuation from the previous
AV-latent tail, adaptive Drift-Control video masking, Soft AV audio continuity, overlap removal, and final synchronized assembly. Extend the result by increasing
the segment count—without generic Loop nodes or duplicated sampler chains. Practical length is limited
only by local VRAM, RAM, disk space, and ComfyUI execution limits.

For long-form digital humans, standalone audio can be set to **Locked Original Audio**. The source
waveform is sliced on the timeline and injected through the native AV-latent mask/sigma path, so lip
motion remains audio-driven while the final soundtrack preserves the uploaded recording unchanged.

[Download the all-in-one workflow](example_workflows/MiniMaxH3全功能合一完全体导演台工作流.json) ·
[Chinese guide](docs/FINITE_SEGMENT_EXPANSION_CN.md) ·
[Chinese prompt specification](docs/MiniMax_H3_循环分段提示词_Agent规范.md)

[![Lightweight unlimited-length workflow](https://github.com/Songssx/ComfyUI-MiniMaxH3-TimelineDirector/releases/download/v0.6.0/infinite-workflow.webp)](example_workflows/MiniMaxH3全功能合一完全体导演台工作流.json)

## SelfLift two-stage sampling: fast 75% low-res + 25% high-res generation

The Material Planner now integrates a MiniMax H3 adaptation of SelfLift progressive-resolution
sampling. Enable **Two-stage sampling**, select an H3 Latent Upscaler from
`ComfyUI/models/latent_upscale_models/`, and set **High-resolution sampling steps**. A recommended
starting point is `25%` of the scheduler's total steps: for an 8-step schedule, set 2 high-resolution
steps to run `6 low-resolution steps + latent lift + 2 high-resolution steps`. The high-resolution
value must be greater than zero and lower than the scheduler's total step count.

![Two-stage toggle, model selector, and high-resolution step control](docs/images/two-stage-controls.png)

This is not a per-segment upscale shortcut. Every later segment carries both the preceding native
low-resolution latent tail and the final high-resolution context, with Drift-Control applied at both
resolution stages. The resulting long-video path avoids progressive quality loss from repeated
resizing or VAE round trips and removes the blur, white flashes, and visible seams normally associated
with multi-segment generation.

Creator benchmark: a `1536×832`, `29-second` video rendered directly in approximately `10 minutes`
with a `75%` low-resolution / `25%` high-resolution schedule. Actual speed depends on GPU, VRAM,
model, step count, and reference complexity. When standalone audio is locked or reference-video source
audio is enabled, the native zero-denoise AV path restores one continuous source waveform; creator
tests retain `99%+` content and timing consistency. The final MP4 saver may still re-encode audio.

One workflow covers text-to-video, image-to-video, audio-reference generation, image plus audio,
reference-video editing, character replacement, motion transfer, digital-human lip sync, and
multi-segment long videos without visible seams or progressive degradation.

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
- Native text-to-video: with no uploaded media and no segment windows, Finite Segment Sampling internally creates a standard empty H3 AV latent from the Global Prompt and current GEN duration. Manual windows extend the same path to long-form T2V.
- Bound source audio follows video edits and can be disabled independently.
- Silent low-resolution monitoring proxies up to `480×270 / 12fps`.
- Multi-select, external file drop, deletion, and drag reordering for image/audio bins. The global
  standalone image and audio libraries have no upload-count limit; each generated segment still follows
  MiniMax H3's limit of at most 9 reference images and 3 reference audio clips.
- Locked-original-audio mode for long-video digital humans and singing avatars, with segment-aware AV
  latent locking and unchanged source-audio assembly.
- Stable `<Picture N>`, `<Video N>`, and `<Audio N>` ordering from UI to H3 inputs.
- Global and per-segment prompts: the global prompt is reused only when all segment prompts are empty; entering any segment prompt requires completing every segment and disables the global prompt.
- Decode-time resizing to the node's `width × height` for VRAM protection.
- Built-in two-stage sampling for every segment, including native low-resolution tail carry, learned H3 latent lifting, and high-resolution Drift-Control continuation; `comfyui-SelfLift` is not required.
- In both one-stage and two-stage reference-video generation, enabled Video Original Audio is automatically locked through the native AV path and restored as one continuous original waveform. Disabling it fixes the AV audio stream and final master to silence; an explicitly uploaded locked audio asset takes priority.
- Segmented digital-human generation with locked source audio on the native AV mask/sigma path, preserving the soundtrack and lip-sync guidance through two-stage sampling.
- Separate merged outputs for timeline soundtracks and standalone reference audio.
- Timeline state is serialized into the ComfyUI workflow JSON.

## Main long-video workflow nodes

| Node | Purpose |
| --- | --- |
| **MiniMax H3 Material Planner** | Edits media and outputs a compact H3 plan plus an ordered Omni media bundle. |
| **MiniMax H3 Omni Media-Bundle Prompt Bridge** | Sends the bundle to an installed Prompt Rewriter Omni backend and returns only `rewritten_prompt`. |
| **MiniMax H3 Finite Segment Sampling** | Expands an acyclic graph for direct-latent continuation, masking, sampling, deduplication, and assembly. |
| **MiniMax H3 native-loop node set** | Splits segment selection, continuation preparation, sampling, and assembly for free composition inside ComfyUI `Start Loop / End Loop`. |
| **MiniMax H3 Preset Export** | Connects to Material Plan or Segment Plan and saves configuration-only or complete media-bearing preset folders. |
| **MiniMax H3 Local Preset Loader** | Finds local presets and feeds the Material Planner's new Import Preset input. |
| **MiniMax H3 Timeline Director (Compatibility)** | Preserves the original all-in-one workflow and older saved workflows. |

Long-video generation needs only **Material Planner Segment Plan → Finite Segment Sampling**. The Plan Encoder is also public now so native Loop workflows can place it explicitly inside the loop body.

### Local presets

Preset Export supports `configuration` (timeline and creative settings only) and `complete` (also copies
referenced video, image, and audio files). It creates an ordinary folder under
`ComfyUI/output/MiniMaxH3_Presets/`; no ZIP is required. Copy that folder to the same location on another
installation, refresh Local Preset Loader, and connect it to Material Planner's **Import Preset** input. The
first run writes all media, segment timings, and per-segment assignments back into the planner UI. The loader
can then be disconnected without losing the imported state. **Import preset** remains available for loading it
into the UI immediately before a run.

Presets intentionally omit workflows, model/LoRA selections, plugin versions, and ComfyUI versions. A complete
preset materializes media into the fixed `ComfyUI/input/minimax_h3_timeline_director/presets/` subtree while
leaving the shared preset folder unchanged.

### Native ComfyUI Loop workflow

The split nodes can drive ComfyUI's native generic loop. Connect **Initialize Segment Loop** state to
`Start Loop.initial_iteration_value` and its count to `num_iterations`. Inside the loop, use
`iteration_index → Select Loop Segment → Plan Encoder → Prepare Loop Segment`, then place either a
normal sampler or the bundled H3 two-stage sampler and decode the result. Feed **Accumulate Loop Segment**
state to both `End Loop.next_iteration_value` and `output_value`; connect `End Loop.outputs` to
**Finish Segment Loop**. The legacy one-node Finite Segment Sampling path remains available for saved workflows.

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

The two-stage runtime is bundled with this plugin; do not install `comfyui-SelfLift` separately. Two-stage sampling still requires a compatible MiniMax H3 latent-upscaler checkpoint under `ComfyUI/models/latent_upscale_models/`; the Material Planner lists models from that standard directory automatically.

The source UI is English. Simplified Chinese is provided through ComfyUI's official localization
system and follows the language selected in ComfyUI settings; restart or reload the frontend after
changing the locale.

### Requirements

- A recent ComfyUI build with the native MiniMax H3 nodes; `MiniMaxH3AddGuide` is additionally required only when Guides are used.
- MiniMax H3 Ref2VA model, CLIP, video VAE, and audio VAE.
- Python 3.10 or newer.
- ComfyUI's `imageio-ffmpeg` package for low-resolution preview proxies.

No extra pip dependency is declared. The plugin uses PyAV, Pillow, NumPy, PyTorch, torchaudio, aiohttp, and imageio-ffmpeg normally included with a compatible ComfyUI installation.

## Example workflows

The plugin ships three example workflows. The first is the normal generation entry point, the second adds Omni prompt expansion, and the third demonstrates finite-segment generation with ComfyUI's native Loop nodes.

### 1. All-in-One Full Timeline Director (recommended)

[Download workflow](example_workflows/MiniMaxH3全功能合一完全体导演台工作流.json)

This is the **all-task, lightweight, no-rewiring** workflow. Configure only the Material Planner's media, time windows, and prompts to run:

- Text-to-video with no media, as one segment.
- Long-form text-to-video with no media and multiple segments.
- Single-segment image-reference generation.
- Multi-segment image-reference generation.
- Single-segment image-and-audio reference generation.
- Multi-segment image-and-audio generation and digital-human lip sync.
- Single-segment editable-video reference, character replacement, and motion transfer.
- Manually segmented long-video reference generation, character replacement, motion transfer, and final AV assembly.

Connect the Material Planner's **Segment Plan** directly to **MiniMax H3 Finite Segment Sampling**. With no uploaded media it creates an empty AV latent; with references it encodes each segment's assigned media. Drag GEN windows to define duration and seam overlap, reuse one Global Prompt, or enter complete per-segment prompts. The plugin handles legal-frame alignment, Drift-Control, Soft AV, overlap removal, tail trimming, and final assembly.

> The plugin does not auto-segment by reference-media duration or infer whether character identity should continue. Segment ranges, overlaps, and assignments are explicitly controlled on the timeline. For character replacement, use **Editable Reference** in most cases.

### 2. Timeline planning with Prompt generation

[Download workflow](example_workflows/MiniMax_H3时间规划+Prompt提示词生成.json)

This variant adds the **MiniMax H3 Omni Media-Bundle Prompt Bridge**, allowing Prompt Rewriter Omni to inspect ordered images, videos, and audio before expanding an H3 prompt. Use it when multimodal material understanding should precede H3 generation.

> This workflow requires [MiniMax-H3-Prompt-Rewriter-ComfyUI](https://github.com/pytraveler/MiniMax-H3-Prompt-Rewriter-ComfyUI). Follow that project for model, quantization, and VRAM requirements.

### 3. Native Loop finite-segment example

[Download workflow](example_workflows/MiniMaxH3原生Loop有限分段示例工作流.json)

This workflow combines the split segment nodes with ComfyUI's native `Start Loop / End Loop`, making it easy to insert custom processing inside the loop body. It is shipped as a read-only example and retains the user's original configuration.

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

Finite sampling carries the previous sampled AV latent tail directly into the next opening and
avoids an RGB decode/re-encode round trip. Drift-Control is always active and has no user-facing mode
selector. The requested overlap is aligned down to H3's legal temporal grid (for example, 24 becomes
22 and 48 becomes 39), and that same actual value drives latent carry, decoded trimming, and assembly.
The mask adapts both to the aligned overlap's video-token count and to the connected sampler's sigma
schedule, including accelerated 4-step and 8-step schedules. It dynamically re-noises only the disposable video prefix while keeping the seam-side
latent clean. When audio continuation is enabled, the carried overlap stays exact until its final eight
audio-latent ticks, where a half-cosine Soft AV mask releases it into newly generated sound. Assembly
replaces the preceding audio tail with this incoming Soft AV overlap so the transition is retained in the final output. All segments use
exactly the seed shown on the sampling node. The old generic-loop helper nodes and PR #15923 dependency
have been removed.

Drift-Control AV is adapted from
[ComfyUI-MiniMaxH3-Contex-Loop](https://github.com/ethanfel/ComfyUI-MiniMaxH3-Contex-Loop)
under GPL-3.0. It remains experimental and is intended for same-shot long-chain comparisons.

## Credits

- Special thanks to [facok/comfyui-SelfLift](https://github.com/facok/comfyui-SelfLift) for the SelfLift progressive-resolution sampling technology. This plugin deeply adapts that work for MiniMax H3 AV latents, native audio mask/sigma locking, low- and high-resolution long-video continuation, and seam handling, and bundles the required runtime.
- MiniMax H3 learned latent-upscaler compatibility references [LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler).
- The Omni bridge and prompt-generation workflow reference and adapt [pytraveler/MiniMax-H3-Prompt-Rewriter-ComfyUI](https://github.com/pytraveler/MiniMax-H3-Prompt-Rewriter-ComfyUI).
- See [MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3) for the official model and prompt guidance.
- Thanks to the maintainers of ComfyUI's native MiniMax H3 and Guide nodes.

## License

[GPL-3.0](LICENSE)
