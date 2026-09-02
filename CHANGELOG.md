# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project is released under GPL-3.0.

## [Unreleased]

### Changed

- Use English as the base language for node definitions, tooltips, status messages, and the custom timeline UI. Add official ComfyUI `locales/en` and `locales/zh` resources; the dynamic timeline follows the active ComfyUI locale and safely falls back to English.
- Simplify finite-segment sampling by removing the per-segment seed-increment and Guide-mask switches. Every segment now reuses the same seed, and every overlap always uses the linear `0→1` temporal mask.

### Security

- Replace the plugin-owned network-reachable chunk writer with ComfyUI's official `/upload/image` endpoint and keep all timeline uploads in a fixed input subfolder.
- Restrict media inspection and preview generation to direct Timeline Director uploads, change both helpers to POST, and add file-size, duration, dimension, concurrency, timeout, and proxy-cache limits.
- Keep detailed decoder/FFmpeg failures in server logs while returning only bounded public errors to browser clients.

## [0.6.0] - 2026-09-01

### Added

- Add optional `提示词序号` input to the material planner for per-segment image/audio selection.
- Add an explicit segment-count setup flow and drag-and-drop per-segment material boards; Picture/Audio ordinals restart from 1 inside every segment.
- Add a Chinese Agent specification for writing parseable finite-segment prompts.

### Compatibility

- Existing workflows with no prompt-index connection or a segment count of 0 continue to use the complete reference library.

### Fixed

- Restore full timeline editing under Nodes 2.0: timeline presses are captured before canvas gestures, active pointers remain captured outside the node, video clips explicitly select their host node, and the cyan generation range now has a full-width move rail plus in-bounds resize handles.
- Allow an empty material plan to run as native MiniMax H3 text-to-video instead of raising “no reference materials”. Empty plans now tokenize only the prompt, create the normal empty AV latent, and skip the Guide dependency entirely.
- Keep timeline dragging and preview playback responsive in Nodes 2.0 by updating only the active clip, generation range, playhead, snap guide, and paired audio geometry during animation frames; the expensive timeline/media DOM rebuild now happens once after drag release.
- Stop the cyan generation-range overlay from stealing pointer input from overlapping video clips. Video bodies and trim handles remain directly draggable, while the `GEN` grip, cyan edge handles, and empty cyan area move or resize the generation range.
- Remove stale invisible DOM hit areas after node resizing or segment-panel contraction: the director now measures natural content height, shrinks as well as grows, and leaves unused DOM-widget space transparent to ComfyUI canvas pointer events.
- Keep the hidden `timeline_data` multiline widget hidden after ComfyUI recreates or resets its DOM wrapper during resize/configure. Its real `.dom-widget` host is now collapsed to zero and cannot intercept canvas drags.
- Allow independent image/audio cards to be copied into per-prompt segment bins while retaining move-based reordering inside the source library. This fixes drag-over highlighting followed by a cancelled drop.
- Lay out multiple image/audio cards horizontally inside each per-prompt segment bin.
- Keep the custom director DOM host at its measured content height and retain a stable node-chrome allowance, preventing Nodes 2.0 from shrinking the node to half-height after selection or resize.

### Changed

- Split the finite long-video path into a pure `MiniMax H3 有限分段展开` planning node and a separate `MiniMax H3 有限分段采样` graph-expansion node. Sampler, scheduler, model, CLIP, and VAEs are no longer inputs of the planning node.

### Removed

- Remove the old generic-loop helper nodes, Loop-dependent workflows/tests/docs, and the ComfyUI PR #15923 runtime dependency.

### Experimental

- Add plugin-owned finite planning and sampling for known segment counts. It performs per-segment selection/encoding/sampling, direct AV-latent continuation, linear temporal masking, overlap removal, and ordered image/audio assembly.
- Add `MiniMax时间线插件内置有限分段工作流.json`, using standard sampler/scheduler/video nodes around the two finite nodes.
- Verify the finite path end to end at 512x288: two 56-frame segments with a 22-frame overlap produced exactly 90 frames at 24 fps with audio.
- Add a dynamic 0→1 linear temporal noise mask to latent-loop continuation. The mask length follows the aligned overlap frames, directly places the previous sampled AV-latent tail at the next segment's opening, and progressively releases video/audio denoising toward the end of the overlap.
- Add an opt-in `MiniMax H3 Direct Latent Guide` node for controlled continuation tests that reuse a sampled H3 video-latent tail without an RGB decode/encode round trip.
- Add an objective video-difference node and a reproducible API workflow comparing native RGB Guide, direct latent Guide, and a single VAE round trip. Production planner, encoder, and compatibility-director behavior is unchanged.

## [0.4.1] - 2026-08-27

### Fixed

- Keep the director DOM fully inside the node after manual width/height resizing by measuring wrapped content, accounting for ComfyUI DOM-widget chrome, and automatically enforcing the resulting minimum node height.
- Allow narrow layouts to wrap settings and inspector controls as complete fields instead of squeezing Chinese labels into vertical characters.

## [0.4.0] - 2026-08-27

### Added

- Split workflow architecture with `MiniMax H3 Material Planner` and `MiniMax H3 Plan Encoder`, removing the dependency cycle when timeline media is inspected by `MiniMax-H3 Prompt Rewriter Omni`.
- Compact `MINIMAX_H3_OMNI_MEDIA_BUNDLE` connection that carries exact Picture, Video, standalone Audio, and paired video-soundtrack order through one socket.
- `MiniMax H3 Omni Media-Bundle Prompt Bridge`, which calls the installed Prompt Rewriter Omni backend and returns only `rewritten_prompt`.

### Changed

- Material Planner outputs were reduced from 23 sockets to two: the H3 plan and the ordered Omni media bundle.
- Every reference video is now strictly cropped to its intersection with the cyan generation range. Outside source frames no longer enter prompt rewriting, H3 video-reference encoding, or per-clip Guides.
- Intersecting videos are numbered left-to-right on the timeline, and the same interval plan is shared by the Omni bridge and final H3 encoder.
- The original monolithic Timeline Director remains available as a backward-compatible node.

### Documentation

- Added a Chinese operational guide for video-generation agents covering long-video segmentation, fixed-Guide overlap, H3 prompt alignment, audio continuity, reference ordering, and deduplicated assembly.
- Added three lightweight example workflows for the compatibility timeline, split planner/encoder, and Prompt Rewriter Omni pipeline.
- Reworked the Chinese and English READMEs into a shorter quick-start guide with compressed workflow screenshots, explicit Prompt Rewriter dependency information, and project credits.

## [0.3.2] - 2026-08-27

### Added

- Video, image, and audio picker buttons now support selecting and importing multiple files in one operation.

### Fixed

- Mouse-wheel events over the director DOM are forwarded to the ComfyUI canvas so canvas zoom continues to work under the cursor.
- Reduced the director DOM widget height from 750 to its 674-pixel content height and removed the forced oversized node height.

## [0.3.1] - 2026-08-26

### Added

- Drop image, audio, and video files directly anywhere inside the director widget to upload them to the correct media collection.
- A full-widget drop overlay provides clear visual feedback during external file dragging.

### Fixed

- External file drops are captured inside the director and prevented from reaching ComfyUI's canvas handlers, avoiding unwanted Load Image nodes or embedded-workflow loading.

## [0.3.0] - 2026-08-26

### Added

- Per-clip video-purpose selector with `Fixed Guide`, `Editable Reference`, and `Boundary Only` modes.
- Editable-reference mode for character, clothing, and style replacement: the selected overlap becomes `<Video N>` without any hard guide.
- Boundary-only mode keeps the overlap as `<Video N>` while anchoring only its first and last frames.
- Drag-and-drop reordering for standalone image and audio bins; prompt ordinals and backend `ref_image_N` / `ref_audio_N` inputs update immediately.

### Compatibility

- Existing workflows and newly uploaded clips default to `Fixed Guide`, preserving the 0.2 behavior until the user explicitly changes a clip mode.

## [0.2.0] - 2026-08-26

### Added

- Native `MiniMaxH3AddGuide` integration for fixed image, video-clip, and optional soundtrack guides at generated-frame positions.
- Timeline visualization of legal fixed-guide frame counts.

### Changed

- Video overlap inside the cyan range is now hard-anchored as a guide; only source context outside crossed edges becomes an ordinary `<Video N>` reference.
- Empty gaps now anchor the nearest left/right stills at the generated first/last frame without consuming `<Picture>` slots.
- Multi-frame guides follow H3's official `5 + 17n` constraint; legal batches plus single-frame guides preserve every source frame (24 frames become `22 + 1 + 1`).
- Long fixed overlaps are decoded in bounded 15-second windows at the node canvas resolution to avoid materializing an oversized source-frame tensor.

## [0.1.1] - 2026-08-24

### Added

- Global video-soundtrack reference toggle on the original-audio track. Disabling it keeps video references active while omitting `ref_video_audio_N` inputs.

### Fixed

- Do not create automatic boundary frames when the cyan selection fully contains a reference video or exactly matches its edges.
- Keep the front-end reference-label preview consistent with the backend boundary-frame rules.

## [0.1.0] - 2026-08-23

### Added

- Editable multi-video reference timeline for MiniMax H3 Ref2VA.
- Bound original-audio waveform track for uploaded videos.
- Clip move, trim, split, delete, and precision editing controls.
- Draggable red playhead with low-resolution proxy monitoring.
- Cached `480×270 / 12fps` silent preview proxies.
- Cyan generation range with move, resize, snapping, and gap matching.
- Bidirectional synchronization between the cyan range and `generation_seconds`.
- Partial-overlap reference extraction with paired soundtrack timing.
- Automatic selection-edge boundary frames and empty-gap bridging.
- Standalone reference image and audio bins with independent numbering from 1.
- H3 presentation ordering that keeps independent media labels stable.
- Reference-media resizing to the node output canvas during decoding.
- Chunked media upload endpoints.
- `视频原声合并` timeline-mixed audio output.
- `独立音频合并` concatenated standalone-audio output.
- Workflow JSON persistence, example workflow, and media smoke tests.
- English and Simplified Chinese documentation.
