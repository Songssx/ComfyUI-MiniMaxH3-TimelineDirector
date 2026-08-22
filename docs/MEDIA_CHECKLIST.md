# Documentation Media Checklist / 文档素材清单

This file lists the recommended screenshots and demos for the first GitHub release.

本文件列出首次GitHub发布最值得准备的截图和演示素材。

## Material status / 当前素材状态

Available now / 已提供：

- `workflow-overview.jpg` — complete workflow overview / 完整工作流全景；
- `partial-overlap.jpg` — partial cyan-range example / 局部青色选区案例；
- three standalone reference images / 3张独立参考图片；
- two standalone reference audios / 2段独立参考音频；
- two visually different videos with embedded audio / 2段视觉差异明显且带原声的视频；
- one 15-second partial-selection video with embedded audio / 1段约15秒、带原声的局部选择视频；
- one `2112×1216` high-resolution source with embedded audio / 1段 `2112×1216` 带原声高分辨率视频。

Still optional / 尚未提供但不阻止首发：

- final generated-result comparison / 最终生成结果对比；
- red-playhead preview GIF or MP4 / 红色播放头低清监看动图；
- snapping/editing GIF / 时间线编辑与吸附动图；
- close-up of stable reference numbering and both audio outputs / 稳定编号与两个音频输出的特写截图。

## Priority A — required / 必需

### 1. Hero screenshot / 主视觉截图

- Show the complete node at a readable zoom.
- Include at least two video clips, visible waveforms, the cyan range, red playhead, preview monitor, one standalone image, and two standalone audios.
- Keep the node fully inside its border and avoid unrelated floating menus.

- 完整显示节点并保证文字可读。
- 最好包含两段视频、波形、青色选区、红色播放头、低清监看、1张独立图片和2段独立音频。
- 节点边框完整，避免无关菜单遮挡。

Recommended file: `docs/images/hero-timeline.png`

### 2. Workflow overview / 工作流全景

- Show the Timeline Director connected to CLIP, video VAE, audio VAE, guider, sampler, decoder, and save nodes.
- Make all four outputs visible, including both `AUDIO` outputs.

- 展示导演台与CLIP、视频VAE、音频VAE、引导器、采样器、解码和保存节点的连接。
- 清楚显示4个输出，包括两个新增音频输出。

Recommended file: `docs/images/workflow-overview.png`

### 3. Partial-overlap example / 局部选区案例

- Use a 10-second source video.
- Put the cyan range over only part of it, such as `2–7s`.
- Show the preview at a recognizable frame and the current `<Video 1>` tag.

- 使用一段10秒视频。
- 青色选区只覆盖其中一部分，例如 `2–7s`。
- 显示监看画面和 `<Video 1>` 标签。

Recommended file: `docs/images/partial-overlap.png`

### 4. Gap-bridge example / 视频空隙桥接案例

- Place two visually different clips with a clear gap.
- Match the cyan range exactly to the gap.
- Ideally include the generated result or a before/after comparison.

- 放置两段视觉差异明显的视频并在中间留出空隙。
- 让青色选区精确匹配空隙。
- 最好附上生成结果或前后对比。

Recommended files:

```text
docs/images/gap-bridge-timeline.png
docs/images/gap-bridge-result.png
```

## Priority B — strongly recommended / 强烈建议

### 5. Numbering close-up / 编号特写

Show:

```text
Standalone image      <Picture 1>
Automatic boundaries <Picture 2..3>
Standalone audios    <Audio 1..2>
Video soundtrack     <Audio 3>
Selected video       <Video 1>
```

Recommended file: `docs/images/reference-numbering.png`

### 6. Low-resolution preview GIF or MP4 / 低清预览动图或视频

- Drag the red playhead and show the monitor changing frames.
- Then press Play Preview and show the red line moving with the proxy.
- 6–12 seconds is enough.

- 拖动红色播放头，让监看画面连续变化。
- 点击播放预览，展示红线随代理视频同步移动。
- 时长6–12秒即可。

Recommended files:

```text
docs/media/preview-scrubbing.gif
docs/media/preview-scrubbing.mp4
```

### 7. Editing and snapping GIF / 编辑与吸附动图

- Move and trim a clip.
- Show the yellow snap guide.
- Resize the cyan range and show `generation_seconds` updating.

Recommended file: `docs/media/editing-and-snapping.gif`

### 8. Audio outputs / 音频输出案例

- Connect `视频原声合并` and `独立音频合并` to waveform preview or audio-save nodes.
- If possible, show a timeline gap becoming silence in the merged waveform.

Recommended file: `docs/images/audio-outputs.png`

## Priority C — optional / 可选

- 4K source versus protected target-resolution comparison.
- Large-file chunked-upload progress.
- Split-at-playhead operation.
- Multi-video reference limit demonstration.
- A short final generated video showing identity, motion, and audio reference usage.
- A 30–60 second narrated overview video in Chinese, with optional English subtitles.

## Capture guidance / 截图建议

- Prefer PNG for UI screenshots.
- Use 1440p or higher capture resolution when possible.
- Keep ComfyUI zoom between 70% and 100% so labels remain readable.
- Hide personal paths, API keys, usernames, and unrelated workflows.
- Use media that can be redistributed publicly.
- For before/after cases, keep aspect ratio and framing consistent.

- UI截图优先使用PNG。
- 建议使用1440p或更高分辨率录制。
- ComfyUI缩放建议70%–100%，确保文字可读。
- 隐藏个人路径、API密钥、用户名和无关工作流。
- 使用允许公开再分发的素材。
- 前后对比保持相同比例和构图。

## Rights confirmation / 素材权利确认

Before publishing, confirm that every screenshot, image, video, audio clip, model output, logo, and character shown in the documentation may be publicly redistributed in a GitHub repository.

发布前请确认文档中出现的截图、图片、视频、音频、模型输出、Logo和角色均允许在GitHub仓库中公开展示和再分发。
