# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project has not yet selected a public-release license or final repository versioning policy.

## [Unreleased]

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

## [0.1.0] - Pre-release

- Initial local development milestone.
