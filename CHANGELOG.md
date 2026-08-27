# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project is released under GPL-3.0.

## [Unreleased]

### Documentation

- Added a Chinese operational guide for video-generation agents covering long-video segmentation, fixed-Guide overlap, H3 prompt alignment, audio continuity, reference ordering, and deduplicated assembly.

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
