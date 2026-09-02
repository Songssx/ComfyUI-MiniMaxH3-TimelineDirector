import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const TIMELINE_NODE_NAMES = new Set(["MiniMaxH3TimelinePlanner", "MiniMaxH3TimelineDirector"]);
const STYLE_ID = "m3td-style";
const MAX_UPLOAD_BYTES = 512 * 1024 * 1024;
const UPLOAD_SUBFOLDER = "minimax_h3_timeline_director";
const DIRECTOR_HEIGHT = 674;

const TIMELINE_EN = {
  brandPlanner: "MiniMax H3 Material Planner", brandDirector: "MiniMax H3 Timeline Director (Compatibility)",
  addVideo: "＋ Video", addImage: "＋ Image", addAudio: "＋ Audio", splitAtPlayhead: "✂ Split at Playhead", deleteClip: "Delete Clip", ready: "Ready",
  selectionStart: "Selection start", referenceDuration: "Reference duration", zoom: "Zoom", fitAll: "Fit all", matchNearestGap: "Match nearest gap",
  materialSegments: "Material segments", updateSegments: "Update segments", timelineHelp: "Drag clips/playhead · Edge snapping · Selection duration = generation duration",
  referenceVideo: "Reference video", videoAudio: "Video audio", off: "Off", on: "On", noClipSelected: "No clip selected",
  previewEmpty: "Move the red playhead over a video clip to preview that position", previewTitle: "Low-resolution monitor · up to 480×270 / 12 fps",
  noPreviewVideo: "No video is available for preview", playPreview: "▶ Play preview", pausePreview: "❚❚ Pause preview",
  previewNote: "Preview uses a low-resolution silent proxy only. Generation reads the original video; the track switch controls whether source audio is referenced.",
  independentImages: "Independent reference images ({count}/9)", independentAudio: "Independent reference audio ({count}/3)",
  dragSortPictures: "Drag to reorder · <Picture i>", dragSortAudio: "Drag to reorder · <Audio j>", assignByPrompt: "Assign materials by prompt index",
  segmentNote: "Drag from the libraries above; Picture / Audio numbering restarts at 1 for each segment", promptLabels: "Prompt labels:",
  audioReferenceOn: "Video source-audio reference enabled", audioReferenceOff: "Video source-audio reference disabled",
  externalDrop: "Drop to import video, reference images, or reference audio", uploadBusy: "A file is still uploading; try again shortly",
  unsupportedFile: "Unsupported file. Drop an image, audio file, or video.", importedSome: "Imported {accepted} files; ignored {rejected} unsupported files",
  disableVideoAudio: "Click to keep the video reference but omit its source audio", enableVideoAudio: "Click to restore source-audio reference",
  moveGenerationRegion: "Move generation region", adjustGenerationStart: "Adjust generation-region start", adjustGenerationEnd: "Adjust generation-region end", movePlayhead: "Move playhead",
  frames: "{count} frames", editable: "EDIT replaceable", clipMeta: "{duration}s · source {source}s",
  proxyGenerating: "Generating a low-resolution proxy; the first preview may take a moment…", proxyGeneratingStatus: "Generating low-resolution preview: {name}",
  proxyReady: "Low-resolution preview ready: {name}", proxyFailed: "Preview generation failed: {error}", previewFailed: "Preview failed: {error}",
  noClipAtPlayhead: "No video clip at the red playhead", timelineAndSourceTime: "{timeline} · source {source}", movePlayheadFirst: "Move the red playhead onto a video clip first",
  noClipInspector: "No clip selected. Click a video clip to enter its position and trim values precisely.", start: "Start", sourceIn: "Source in", clipDuration: "Clip duration",
  videoPurpose: "Video purpose", fixedGuide: "Fixed Guide", editableReference: "Editable reference", boundaryOnly: "Fixed boundaries only",
  sourceAudioOn: "✓ Source-audio reference on", sourceAudioOff: "⊘ Source-audio reference off", noSourceAudio: "— No source audio",
  editableModeStatus: "Editable reference: the original subject is not fixed", boundaryModeStatus: "Only the first/last boundary frames are fixed", fixedGuideStatus: "Fixed Guide: preserve the original image frame by frame",
  dragReorder: "Drag to reorder references", imageOrderUpdated: "Image reference order updated", audioOrderUpdated: "Audio reference order updated",
  segmentsCreated: "Created {count} material segments. Drag images and audio into the corresponding segment.", segmentsDisabled: "Material segmentation disabled; all images and audio will be used.",
  segmentAssetTitle: "Drag to reorder within this segment, or reuse in another segment", segmentTitle: "Segment {index}", segmentPromptMatch: "Matches prompt index {index} · numbering starts at 1",
  segmentImages: "Reference images (drop here)", segmentAudio: "Reference audio (drop here)", segmentUpdated: "Segment {index} materials updated", segmentOrderUpdated: "Segment {index} material order updated",
  normalVideoRefs: "Standard video references <Video 1..{count}>", noNormalVideoRefs: "No standard video references", independentPictures: "Independent images <Picture 1..{count}>", noIndependentPictures: "No independent images",
  nativeFixed: "native fixed {count} segment(s)", boundaryFixed: "boundary fixed {count} segment(s)", guideSummary: "{parts}/{frames} frames", gapGuide: "gap boundary Guide {count} frames", noFixedGuide: "No fixed Guide",
  standaloneAudioRefs: "Independent audio <Audio 1..{count}>", noStandaloneAudio: "No independent audio", videoAudioDisabled: "Video audio: reference disabled", pairedVideoAudio: "Video audio <Audio {start}..{end}>", noVideoAudioLabels: "No video-audio labels",
  segmentFilterSummary: "{count} material segments (filtered by prompt index)", noSegmentFilter: "Material segmentation not enabled",
  playheadInsideClip: "The playhead must be inside the selected clip", noMatchingGap: "There is no gap between current video clips", selectionMatchedGap: "Generation selection matched a {duration}-second gap",
  maxImages: "Up to 9 images", maxAudio: "Up to 3 independent audio clips", emptyFile: "The file is empty", tooLarge: "The file exceeds the plug-in's 512 MiB safety limit",
  uploading: "Uploading {name} through ComfyUI", uploadSizeHint: "; adjust ComfyUI --max-upload-size and restart", uploadFailed: "ComfyUI upload failed: HTTP {status}{hint}", checking: "Inspecting {name}", mediaCheckFailed: "Media inspection failed: HTTP {status}",
  noVideoTrack: "The uploaded file contains no video track", noAudioTrack: "The uploaded file contains no audio track", addedFile: "Added {name}", failed: "Failed: {error}",
};

let timelineMessages = { ...TIMELINE_EN };
let timelineLocalePromise;
const activeLocale = () => {
  const raw = app.ui?.settings?.getSettingValue?.("Comfy.Locale") || app.ui?.settings?.getSettingValue?.("Comfy.Locale.Language") || navigator.language || "en";
  return String(raw).toLowerCase().startsWith("zh") ? "zh" : "en";
};
async function ensureTimelineLocale() {
  if (!timelineLocalePromise) timelineLocalePromise = (async () => {
    try {
      const response = await api.fetchApi("/i18n");
      if (!response.ok) return;
      const translations = await response.json();
      const messages = translations?.[activeLocale()]?.MiniMaxH3TimelineDirector?.timeline;
      if (messages && typeof messages === "object") timelineMessages = { ...TIMELINE_EN, ...messages };
    } catch (error) { console.warn("[MiniMaxH3TimelineDirector] Unable to load localization", error); }
  })();
  return timelineLocalePromise;
}
function tr(key, values = {}) {
  const message = timelineMessages[key] ?? TIMELINE_EN[key] ?? key;
  return String(message).replace(/\{(\w+)\}/g, (_, name) => values[name] ?? `{${name}}`);
}

function installStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .m3td { --bg:#11141b; --panel:#191e28; --line:#30384a; --text:#e9eef8; --muted:#919bad;
      --cyan:#43d9d1; --blue:#477ff0; --amber:#f3af4e; --red:#ef6a77; box-sizing:border-box;
      position:relative; width:100%; max-width:100%; height:auto; min-height:0; color:var(--text); background:var(--bg); border:1px solid #2b3241;
      border-radius:9px; overflow:hidden; font:12px/1.35 Inter,Segoe UI,Arial,sans-serif; user-select:none; }
    .m3td-widget-host { pointer-events:none !important; }
    .m3td-widget-host .m3td { pointer-events:auto; touch-action:none; }
    .m3td * { box-sizing:border-box; }
    .m3td button,.m3td input { font:inherit; }
    .m3td-head { display:flex; align-items:center; gap:6px; padding:8px; background:linear-gradient(180deg,#242a37,#1c222d);
      border-bottom:1px solid var(--line); flex-wrap:wrap; }
    .m3td-brand { font-weight:700; letter-spacing:.2px; color:#fff; margin-right:8px; }
    .m3td-btn { height:28px; border:1px solid #3b4558; color:#dce5f5; background:#252d3a; border-radius:5px;
      padding:0 9px; cursor:pointer; display:inline-flex; align-items:center; gap:5px; }
    .m3td-btn:hover { background:#303a4b; border-color:#516079; }
    .m3td-btn.danger:hover { color:#fff; background:#6d2833; border-color:#a64250; }
    .m3td-btn:disabled { opacity:.42; cursor:default; }
    .m3td-spacer { flex:1; }
    .m3td-status { color:var(--muted); max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .m3td-settings { display:flex; align-items:center; gap:8px 12px; padding:7px 10px; border-bottom:1px solid var(--line); background:#151a22; flex-wrap:wrap; }
    .m3td-field { display:flex; flex:0 0 auto; align-items:center; gap:5px; color:var(--muted); white-space:nowrap; }
    .m3td-field input,.m3td-field select { width:72px; height:25px; padding:2px 5px; color:var(--text); background:#0d1118;
      border:1px solid #333d50; border-radius:4px; outline:none; user-select:text; }
    .m3td-field input:focus,.m3td-field select:focus { border-color:var(--cyan); }
    .m3td-help { flex:1 1 220px; margin-left:auto; color:#9da9bc; text-align:right; }
    .m3td-timeline-shell { display:grid; grid-template-columns:108px minmax(0,1fr); border-bottom:1px solid var(--line); }
    .m3td-labels { background:#151a22; border-right:1px solid var(--line); padding-top:26px; }
    .m3td-track-label { display:flex; height:94px; align-items:center; padding:0 10px; border-top:1px solid #272e3b; color:#aab5c7; }
    .m3td-track-label.audio { height:50px; color:#c0a36f; }
    .m3td-audio-toggle { margin-left:auto; height:22px; padding:0 6px; border:1px solid #6c5638; border-radius:4px;
      color:#f3cf92; background:#382d20; cursor:pointer; font-size:10px; }
    .m3td-audio-toggle.off { color:#c3cad5; background:#282d36; border-color:#4c5565; }
    .m3td-viewport { position:relative; overflow:auto; background:#0e1219; scrollbar-color:#49556a #171c25; }
    .m3td-stage { position:relative; min-width:100%; height:170px; touch-action:none; }
    .m3td-ruler { position:relative; height:26px; border-bottom:1px solid #2c3443; background:#131821; }
    .m3td-tick { position:absolute; bottom:0; width:1px; height:8px; background:#556074; color:#8490a4; }
    .m3td-tick.major { height:13px; background:#78849a; }
    .m3td-tick span { position:absolute; left:4px; top:-11px; white-space:nowrap; font-size:10px; }
    .m3td-track { position:relative; height:94px; border-bottom:1px solid #262d3a;
      background-image:linear-gradient(90deg,rgba(255,255,255,.027) 1px,transparent 1px); }
    .m3td-track.audio { height:50px; background-color:#111720; }
    .m3td-track.audio.muted .m3td-audio-clip { opacity:.28; filter:grayscale(1); }
    .m3td-clip { position:absolute; top:8px; height:78px; min-width:10px; overflow:hidden; border:1px solid #5688ec;
      border-radius:5px; background:#223c6e; cursor:grab; box-shadow:0 3px 10px #0007; touch-action:none; }
    .m3td-clip.selected { border:2px solid #b9ddff; box-shadow:0 0 0 2px #328bff99,0 5px 14px #0009; }
    .m3td-clip video { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; opacity:.62; pointer-events:none; }
    .m3td-clip-shade { position:absolute; inset:0; background:linear-gradient(180deg,#0002,#061329cc); }
    .m3td-clip-name { position:absolute; left:9px; right:8px; top:7px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
      font-weight:600; text-shadow:0 1px 2px #000; }
    .m3td-clip-meta { position:absolute; left:9px; bottom:6px; color:#c8d9f7; text-shadow:0 1px 2px #000; }
    .m3td-clip-ref { position:absolute; right:6px; top:6px; z-index:3; padding:1px 4px; border-radius:3px;
      color:#dffcff; background:#102432dc; font-size:10px; font-weight:700; }
    .m3td-clip-ref.guide { top:24px; color:#78fff5; border:1px solid #43d9d177; }
    .m3td-clip-ref.edit { top:24px; color:#ffd58a; border:1px solid #f3af4e88; }
    .m3td-clip-ref.boundary { top:24px; color:#c7b7ff; border:1px solid #987cff88; }
    .m3td-handle { position:absolute; top:0; bottom:0; width:12px; z-index:4; cursor:ew-resize; touch-action:none; }
    .m3td-handle.left { left:0; } .m3td-handle.right { right:0; }
    .m3td-audio-clip { position:absolute; top:5px; height:40px; overflow:hidden; border:1px solid #a77636; border-radius:4px;
      background:#44351f; opacity:.92; }
    .m3td-wave { width:100%; height:100%; display:block; }
    .m3td-selection { position:absolute; top:26px; height:144px; z-index:8; border:2px solid var(--cyan);
      background:rgba(35,211,199,.10); box-shadow:inset 0 0 25px #43d9d116; pointer-events:none; cursor:move; }
    .m3td-selection .m3td-sel-move { position:absolute; top:0; left:12px; right:12px; height:18px; padding:1px 4px 0;
      pointer-events:auto; cursor:grab; touch-action:none; font-size:9px; line-height:14px; font-weight:800; color:#72fff5;
      background:linear-gradient(90deg,#123f43e6,#123f4366 34px,transparent 96px); border-radius:0 0 3px 3px; }
    .m3td-selection .m3td-sel-handle { position:absolute; top:0; bottom:0; width:12px; pointer-events:auto; touch-action:none;
      background:#43d9d166; cursor:ew-resize; }
    .m3td-selection .left { left:0; } .m3td-selection .right { right:0; }
    .m3td-playhead { position:absolute; top:0; bottom:0; width:9px; margin-left:-4px; z-index:11; cursor:ew-resize; touch-action:none; }
    .m3td-playhead::before { content:""; position:absolute; left:0; top:0; border-left:4px solid transparent;
      border-right:4px solid transparent; border-top:7px solid #ff737d; }
    .m3td-playhead::after { content:""; position:absolute; left:4px; top:0; bottom:0; width:1px; background:#ff737d; }
    .m3td-snap-guide { position:absolute; top:0; bottom:0; width:1px; z-index:12; pointer-events:none;
      background:#ffe178; box-shadow:0 0 5px #ffe178; }
    .m3td-inspector { display:flex; flex-wrap:wrap; gap:6px 10px; align-items:center; min-height:38px; padding:6px 10px; background:#171c25;
      border-bottom:1px solid var(--line); color:var(--muted); }
    .m3td-inspector strong { color:#dfe8f7; max-width:190px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .m3td-inspector .m3td-field input { width:66px; }
    .m3td-inspector .m3td-field select { width:98px; }
    .m3td-preview { display:grid; grid-template-columns:minmax(260px,380px) minmax(0,1fr); gap:10px; min-height:174px;
      padding:8px 10px; border-bottom:1px solid var(--line); background:#0d1118; }
    .m3td-preview-screen { position:relative; display:flex; align-items:center; justify-content:center; height:156px; overflow:hidden;
      border:1px solid #30394a; border-radius:6px; background:#05070a; }
    .m3td-preview-video { display:none; width:100%; height:100%; object-fit:contain; background:#000; }
    .m3td-preview-empty { padding:15px; text-align:center; color:#717d91; }
    .m3td-preview-side { min-width:0; display:flex; flex-direction:column; justify-content:center; align-items:flex-start; gap:9px; }
    .m3td-preview-title { color:#dce8f8; font-weight:700; }
    .m3td-preview-time { color:#69e4dc; font:600 18px/1.1 ui-monospace,Consolas,monospace; }
    .m3td-preview-name { max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#98a5b9; }
    .m3td-preview-note { color:#718096; line-height:1.45; }
    .m3td-assets { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:8px; padding:8px; height:154px; background:#10151d; }
    @media (max-width:680px) { .m3td-preview { grid-template-columns:1fr; min-height:260px; } .m3td-preview-screen { height:190px; } }
    .m3td-bin { min-width:0; border:1px solid #2d3545; border-radius:6px; overflow:hidden; background:#151a23; }
    .m3td-bin-title { display:flex; align-items:center; justify-content:space-between; height:27px; padding:0 8px; color:#b9c4d6;
      background:#202633; border-bottom:1px solid #30394a; }
    .m3td-bin-list { height:116px; overflow:auto; padding:5px; display:flex; flex-wrap:wrap; align-content:flex-start; gap:5px; }
    .m3td-asset { position:relative; width:82px; height:50px; border:1px solid #394459; border-radius:4px; overflow:hidden;
      background:#242c39; cursor:grab; }
    .m3td-asset:active { cursor:grabbing; }
    .m3td-asset.dragging { opacity:.38; }
    .m3td-asset.drop-before { box-shadow:-3px 0 0 var(--cyan); }
    .m3td-asset.drop-after { box-shadow:3px 0 0 var(--cyan); }
    .m3td-asset img { width:100%; height:100%; object-fit:cover; }
    .m3td-asset.audio { width:120px; color:#e0c28e; padding:7px 20px 5px 7px; }
    .m3td-asset-tag { position:absolute; left:3px; top:2px; z-index:2; padding:1px 3px; border-radius:3px;
      color:#fff4c9; background:#111c; font-size:10px; font-weight:700; }
    .m3td-asset-name { position:absolute; left:3px; right:3px; bottom:2px; padding:1px 2px; overflow:hidden; text-overflow:ellipsis;
      white-space:nowrap; background:#000a; color:#fff; font-size:10px; }
    .m3td-asset-x { position:absolute; right:2px; top:2px; width:17px; height:17px; border:0; border-radius:50%; color:#fff;
      background:#9c3345cc; cursor:pointer; }
    .m3td-segments { padding:8px; border-top:1px solid var(--line); background:#0d1219; }
    .m3td-segments[hidden] { display:none; }
    .m3td-segment-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:7px;
      color:#cbd6e7; }
    .m3td-segment-note { color:#7f8ba0; }
    .m3td-segment-list { display:grid; gap:7px; }
    .m3td-segment { min-width:0; border:1px solid #313a4c; border-radius:6px; overflow:hidden; background:#141a23; }
    .m3td-segment-title { display:flex; align-items:center; justify-content:space-between; min-height:28px; padding:5px 8px;
      color:#dce6f6; background:#202735; border-bottom:1px solid #30394a; }
    .m3td-segment-title small { color:#7f8ba0; }
    .m3td-segment-bins { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:6px; padding:6px; }
    .m3td-segment-bin { min-width:0; min-height:68px; padding:4px; border:1px dashed #3a465b; border-radius:5px;
      background:#101620; }
    .m3td-segment-bin.drag-over { border-color:var(--cyan); background:#102421; }
    .m3td-segment-bin-label { margin:0 0 4px 2px; color:#8e9bb0; font-size:10px; }
    .m3td-segment-bin-list { min-height:46px; display:flex; flex-wrap:wrap; align-content:flex-start; gap:4px; }
    .m3td-segment .m3td-asset { width:72px; height:44px; }
    .m3td-segment .m3td-asset.audio { width:112px; }
    .m3td-foot { display:flex; align-items:center; gap:9px; min-height:31px; padding:5px 9px; color:#8f9bad; background:#141922; }
    .m3td-tags { color:#a9d8d4; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .m3td-progress { width:90px; height:4px; overflow:hidden; border-radius:2px; background:#303746; }
    .m3td-progress > i { display:block; height:100%; width:0; background:var(--cyan); }
    .m3td.external-file-drag::after { content:attr(data-drop-label); position:absolute; inset:7px; z-index:50; display:flex;
      align-items:center; justify-content:center; padding:20px; border:2px dashed var(--cyan); border-radius:8px;
      color:#dffffc; background:#071918ef; box-shadow:inset 0 0 40px #43d9d133; font-size:18px; font-weight:700;
      text-align:center; pointer-events:none; }
  `;
  document.head.appendChild(style);
}

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
const num = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function responseJSON(response) {
  try { return await response.json(); }
  catch (_) { return {}; }
}

function uploadedRelativePath(payload) {
  const name = String(payload?.name || "").replace(/[\\/]+/g, "_");
  const subfolder = String(payload?.subfolder || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (!name) throw new Error("ComfyUI did not return an uploaded filename");
  return subfolder ? `${subfolder}/${name}` : name;
}

function reorderById(items, draggedId, targetId, after = false) {
  const sourceIndex = items.findIndex(item => item.id === draggedId);
  if (sourceIndex < 0 || draggedId === targetId) return false;
  const [moved] = items.splice(sourceIndex, 1);
  const targetIndex = items.findIndex(item => item.id === targetId);
  if (targetIndex < 0) { items.splice(sourceIndex, 0, moved); return false; }
  items.splice(targetIndex + (after ? 1 : 0), 0, moved);
  return true;
}

function isExternalFileDrag(event) {
  const transfer = event.dataTransfer;
  return !!transfer && (transfer.files?.length > 0 || Array.from(transfer.types || []).includes("Files"));
}

function uploadKindForFile(file) {
  const mime = String(file?.type || "").toLowerCase();
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("audio/")) return "audio";
  if (mime.startsWith("video/")) return "video";
  const extension = String(file?.name || "").split(".").pop()?.toLowerCase() || "";
  if (["png","jpg","jpeg","webp","bmp","gif","tif","tiff"].includes(extension)) return "image";
  if (["mp3","wav","flac","m4a","aac","ogg","opus","wma"].includes(extension)) return "audio";
  if (["mp4","mov","mkv","webm","avi","m4v","mpeg","mpg"].includes(extension)) return "video";
  return null;
}

function forwardWheelEvent(event, canvas) {
  if (!canvas) return false;
  event.preventDefault();
  event.stopPropagation();
  return canvas.dispatchEvent(new WheelEvent("wheel", {
    bubbles:true, cancelable:true, composed:true,
    deltaX:event.deltaX, deltaY:event.deltaY, deltaZ:event.deltaZ, deltaMode:event.deltaMode,
    clientX:event.clientX, clientY:event.clientY, screenX:event.screenX, screenY:event.screenY,
    ctrlKey:event.ctrlKey, shiftKey:event.shiftKey, altKey:event.altKey, metaKey:event.metaKey
  }));
}

function emptyState() {
  return { version: 4, fps: 24, selection: { start: 0, duration: 5 }, videoAudioEnabled: true, videoClips: [], images: [], audios: [], segmentConfig:{count:0,segments:[]} };
}

function normalizedAssetIds(values, validIds) {
  const result=[];
  for(const value of Array.isArray(values)?values:[]){
    const id=String(value);
    if(validIds.has(id)&&!result.includes(id))result.push(id);
  }
  return result;
}

function normalizeState(raw) {
  const base = emptyState();
  if (!raw || typeof raw !== "object") return base;
  base.selection.start = Math.max(0, num(raw.selection?.start, 0));
  base.selection.duration = Math.max(5 / 24, num(raw.selection?.duration, 5));
  base.videoAudioEnabled = raw.videoAudioEnabled !== false;
  base.videoClips = Array.isArray(raw.videoClips) ? raw.videoClips.filter(x => x?.file).map(c => ({
    id: c.id || uid(), file: c.file, name: c.name || c.file.split(/[\\/]/).pop(), start: Math.max(0, num(c.start)),
    duration: Math.max(5 / 24, num(c.duration, 5)), trimStart: Math.max(0, num(c.trimStart)),
    sourceDuration: Math.max(0, num(c.sourceDuration, c.duration)), hasAudio: c.hasAudio !== false,
    referenceMode: ["guide","edit","boundary"].includes(c.referenceMode) ? c.referenceMode : "guide",
    proxy: c.proxy || "",
    peaks: Array.isArray(c.peaks) ? c.peaks : [],
  })) : [];
  base.images = Array.isArray(raw.images) ? raw.images.filter(x => x?.file).slice(0, 9).map(a => ({ id:a.id || uid(), ...a })) : [];
  base.audios = Array.isArray(raw.audios) ? raw.audios.filter(x => x?.file).slice(0, 3).map(a => ({ id:a.id || uid(), ...a })) : [];
  const imageIds=new Set(base.images.map(a=>String(a.id))),audioIds=new Set(base.audios.map(a=>String(a.id)));
  const rawConfig=raw.segmentConfig&&typeof raw.segmentConfig==="object"?raw.segmentConfig:{};
  const count=clamp(Math.floor(num(rawConfig.count,0)),0,64);
  const sourceSegments=Array.isArray(rawConfig.segments)?rawConfig.segments:[];
  base.segmentConfig={count,segments:Array.from({length:count},(_,index)=>{
    const segment=sourceSegments[index]&&typeof sourceSegments[index]==="object"?sourceSegments[index]:{};
    return {images:normalizedAssetIds(segment.images,imageIds),audios:normalizedAssetIds(segment.audios,audioIds)};
  })};
  return base;
}

function viewURL(relative) {
  const parts = String(relative).replace(/\\/g, "/").split("/");
  const filename = parts.pop();
  const params = new URLSearchParams({ filename, type: "input" });
  if (parts.length) params.set("subfolder", parts.join("/"));
  return api.apiURL(`/view?${params.toString()}`);
}

class TimelineDirectorUI {
  constructor(node, root, widget, brand = "MiniMax H3 Material Planner") {
    this.node = node;
    this.root = root;
    this.widget = widget;
    this.brand = brand;
    this.state = normalizeState(this.readWidget());
    this.zoom = 64;
    this.selectedId = null;
    this.playhead = this.state.selection.start;
    this.drag = null;
    this.snapGuide = null;
    this.generationSecondsWidget = this.node.widgets?.find(w => w.name === "generation_seconds");
    this._syncingGeneration = false;
    this.uploading = false;
    this.proxyRequests = new Map();
    this.previewRAF = 0;
    this.dragRAF = 0;
    this.layoutRAF = 0;
    this.previewClipId = null;
    this.segmentCountDraft = this.state.segmentConfig.count;
    this.build();
    this.contentResizeObserver = new ResizeObserver(() => this.scheduleNodeHeightSync());
    this.contentResizeObserver.observe(this.root);
    this.bindGenerationWidget();
    this.syncGenerationWidget();
    this.render();
    this.attachGlobalPointerHandlers();
    this.bindExternalFileDrop();
  }

  readWidget() {
    try { return JSON.parse(this.widget?.value || "{}"); } catch (_) { return {}; }
  }

  bindGenerationWidget() {
    const widget = this.generationSecondsWidget;
    if (!widget || widget.__m3tdBound) return;
    const original = widget.callback;
    widget.callback = (...args) => {
      const result = original?.apply(widget, args);
      if (!this._syncingGeneration) {
        const seconds = Math.max(5 / 24, num(widget.value, num(args[0], 5)));
        if (Math.abs(seconds - this.state.selection.duration) > 0.0001) {
          this.state.selection.duration = seconds;
          this.sync(false);
          this.render();
        }
      }
      return result;
    };
    widget.__m3tdBound = true;
  }

  syncGenerationWidget() {
    const widget = this.generationSecondsWidget;
    if (!widget) return;
    const seconds = Math.round(this.state.selection.duration * 1000) / 1000;
    if (Math.abs(num(widget.value, seconds) - seconds) < 0.0001) return;
    this._syncingGeneration = true;
    widget.value = seconds;
    try { widget.callback?.(seconds); } finally { this._syncingGeneration = false; }
  }

  sync(updateGeneration = true) {
    if (updateGeneration) this.syncGenerationWidget();
    if (this.widget) {
      this.widget.value = JSON.stringify(this.state);
      this.widget.callback?.(this.widget.value);
    }
    this.node.setDirtyCanvas?.(true, true);
  }

  canvasScale() {
    const rect = this.stage?.getBoundingClientRect();
    return rect ? rect.width / Math.max(1, this.stage.offsetWidth) : 1;
  }

  timeFromClientX(clientX) {
    const rect = this.stage.getBoundingClientRect();
    return clamp((clientX - rect.left) / (this.zoom * this.canvasScale()), 0, this.timelineDuration());
  }

  referencePlan() {
    const start = this.state.selection.start;
    const end = start + this.state.selection.duration;
    const ordered = [...this.state.videoClips].sort((a,b) => a.start - b.start);
    const epsilon = 1 / 24;
    const clipEnd = c => c.start + c.duration;
    const guidePieces = [];
    const videoPieces = [];
    let pairedAudioCount = 0;
    let hasOverlap = false;
    for (const clip of ordered) {
      const overlapStart = Math.max(start, clip.start), overlapEnd = Math.min(end, clipEnd(clip));
      const overlap = overlapEnd - overlapStart;
      if (overlap <= 0) continue;
      hasOverlap = true;
      const guideFrames = Math.max(1, Math.round(overlap * 24));
      const mode = clip.referenceMode || "guide";
      if (mode === "guide") guidePieces.push({clipId:clip.id, frames:guideFrames, mode, hasAudio:this.state.videoAudioEnabled && !!clip.hasAudio});
      else if (mode === "boundary") guidePieces.push({clipId:clip.id, frames:Math.min(2,guideFrames), mode, hasAudio:false});
      // Only the intersection with the cyan generation range is prompt- and
      // H3-addressable.  Unselected source frames never become Video N.
      for (let remaining of [overlap]) while (remaining >= 5/24 && videoPieces.length < 3) {
        const seconds = Math.min(15, remaining);
        const hasAudio = this.state.videoAudioEnabled && !!clip.hasAudio;
        videoPieces.push({clipId: clip.id, seconds, hasAudio, mode});
        if (hasAudio) pairedAudioCount++;
        remaining -= seconds;
      }
    }
    let gapGuideCount = 0;
    if (!hasOverlap) {
      if (ordered.some(c => clipEnd(c) <= start + epsilon)) gapGuideCount++;
      if (ordered.some(c => c.start >= end - epsilon)) gapGuideCount++;
    }
    return {guidePieces, gapGuideCount, videoPieces, pairedAudioCount};
  }

  snapPoints(excludeClipId = null, includeSelection = true) {
    const points = [0];
    for (const clip of this.state.videoClips) {
      if (clip.id === excludeClipId) continue;
      points.push(clip.start, clip.start + clip.duration);
    }
    if (includeSelection) points.push(this.state.selection.start, this.state.selection.start + this.state.selection.duration);
    return [...new Set(points.map(value => Math.max(0, value)))];
  }

  snapValue(value, points) {
    const threshold = 10 / Math.max(24, this.zoom);
    let best = value, distance = threshold + 1, snapAt = null;
    for (const point of points) {
      const current = Math.abs(point - value);
      if (current <= threshold && current < distance) { best = point; distance = current; snapAt = point; }
    }
    return {value: Math.max(0, best), snapAt};
  }

  snapInterval(start, duration, points) {
    const left = this.snapValue(start, points);
    const right = this.snapValue(start + duration, points);
    if (left.snapAt != null && (right.snapAt == null || Math.abs(left.value - start) <= Math.abs(right.value - (start + duration)))) {
      return {start: Math.max(0, left.value), snapAt: left.snapAt};
    }
    if (right.snapAt != null) return {start: Math.max(0, right.value - duration), snapAt: right.snapAt};
    return {start: Math.max(0, start), snapAt: null};
  }

  timelineGaps() {
    const intervals = [...this.state.videoClips]
      .map(c => ({start:c.start, end:c.start + c.duration}))
      .sort((a,b) => a.start - b.start);
    if (intervals.length < 2) return [];
    const merged = [intervals[0]];
    for (const current of intervals.slice(1)) {
      const last = merged[merged.length - 1];
      if (current.start <= last.end + 1/24) last.end = Math.max(last.end, current.end);
      else merged.push({...current});
    }
    const gaps = [];
    for (let i=0; i<merged.length-1; i++) {
      if (merged[i+1].start - merged[i].end >= 5/24) gaps.push({start:merged[i].end, duration:merged[i+1].start-merged[i].end});
    }
    return gaps;
  }

  build() {
    this.root.className = "m3td";
    this.root.innerHTML = `
      <div class="m3td-head">
        <span class="m3td-brand">${esc(this.brand)}</span>
        <button class="m3td-btn" data-action="video">${esc(tr("addVideo"))}</button>
        <button class="m3td-btn" data-action="image">${esc(tr("addImage"))}</button>
        <button class="m3td-btn" data-action="audio">${esc(tr("addAudio"))}</button>
        <button class="m3td-btn" data-action="split">${esc(tr("splitAtPlayhead"))}</button>
        <button class="m3td-btn danger" data-action="delete">${esc(tr("deleteClip"))}</button>
        <span class="m3td-spacer"></span><span class="m3td-status">${esc(tr("ready"))}</span>
        <span class="m3td-progress"><i></i></span>
      </div>
      <div class="m3td-settings">
        <label class="m3td-field">${esc(tr("selectionStart"))} <input data-field="selectionStart" type="number" min="0" step="0.04"></label>
        <label class="m3td-field">${esc(tr("referenceDuration"))} <input data-field="selectionDuration" type="number" min="0.21" step="0.04"></label>
        <label class="m3td-field">${esc(tr("zoom"))} <input data-field="zoom" type="range" min="24" max="180" step="4"></label>
        <button class="m3td-btn" data-action="fit">${esc(tr("fitAll"))}</button>
        <button class="m3td-btn" data-action="fitGap">${esc(tr("matchNearestGap"))}</button>
        <label class="m3td-field">${esc(tr("materialSegments"))} <input data-field="segmentCount" type="number" min="0" max="64" step="1"></label>
        <button class="m3td-btn" data-action="applySegments">${esc(tr("updateSegments"))}</button>
        <span class="m3td-help">${esc(tr("timelineHelp"))}</span>
      </div>
      <div class="m3td-timeline-shell">
        <div class="m3td-labels"><div class="m3td-track-label">${esc(tr("referenceVideo"))}</div><div class="m3td-track-label audio"><span>${esc(tr("videoAudio"))}</span><button class="m3td-audio-toggle" data-action="videoAudioToggle" type="button">${esc(tr("off"))}</button></div></div>
        <div class="m3td-viewport"><div class="m3td-stage"></div></div>
      </div>
      <div class="m3td-inspector"><span>${esc(tr("noClipSelected"))}</span></div>
      <div class="m3td-preview">
        <div class="m3td-preview-screen"><video class="m3td-preview-video" muted playsinline preload="metadata"></video><div class="m3td-preview-empty">${esc(tr("previewEmpty"))}</div></div>
        <div class="m3td-preview-side">
          <div class="m3td-preview-title">${esc(tr("previewTitle"))}</div>
          <div class="m3td-preview-time">00:00.00</div>
          <div class="m3td-preview-name">${esc(tr("noPreviewVideo"))}</div>
          <button class="m3td-btn" data-action="previewPlay">${esc(tr("playPreview"))}</button>
          <div class="m3td-preview-note">${esc(tr("previewNote"))}</div>
        </div>
      </div>
      <div class="m3td-assets">
        <section class="m3td-bin"><div class="m3td-bin-title"><span>${esc(tr("independentImages",{count:0}))}</span><span>${esc(tr("dragSortPictures"))}</span></div><div class="m3td-bin-list" data-bin="images"></div></section>
        <section class="m3td-bin"><div class="m3td-bin-title"><span>${esc(tr("independentAudio",{count:0}))}</span><span>${esc(tr("dragSortAudio"))}</span></div><div class="m3td-bin-list" data-bin="audios"></div></section>
      </div>
      <div class="m3td-segments" hidden>
        <div class="m3td-segment-head"><strong>${esc(tr("assignByPrompt"))}</strong><span class="m3td-segment-note">${esc(tr("segmentNote"))}</span></div>
        <div class="m3td-segment-list"></div>
      </div>
      <div class="m3td-foot"><strong>${esc(tr("promptLabels"))}</strong><span class="m3td-tags"></span></div>
      <input hidden data-upload="video" type="file" accept="video/*" multiple>
      <input hidden data-upload="image" type="file" accept="image/*" multiple>
      <input hidden data-upload="audio" type="file" accept="audio/*" multiple>
    `;
    this.stage = this.root.querySelector(".m3td-stage");
    this.viewport = this.root.querySelector(".m3td-viewport");
    this.status = this.root.querySelector(".m3td-status");
    this.progress = this.root.querySelector(".m3td-progress i");
    this.inspector = this.root.querySelector(".m3td-inspector");
    this.previewVideo = this.root.querySelector(".m3td-preview-video");
    this.previewEmpty = this.root.querySelector(".m3td-preview-empty");
    this.previewTime = this.root.querySelector(".m3td-preview-time");
    this.previewName = this.root.querySelector(".m3td-preview-name");
    this.previewPlay = this.root.querySelector('[data-action="previewPlay"]');
    this.videoAudioToggle = this.root.querySelector('[data-action="videoAudioToggle"]');
    this.root.querySelector('[data-action="video"]').onclick = () => this.root.querySelector('[data-upload="video"]').click();
    this.root.querySelector('[data-action="image"]').onclick = () => this.root.querySelector('[data-upload="image"]').click();
    this.root.querySelector('[data-action="audio"]').onclick = () => this.root.querySelector('[data-upload="audio"]').click();
    this.root.querySelector('[data-action="split"]').onclick = () => this.splitSelected();
    this.root.querySelector('[data-action="delete"]').onclick = () => this.deleteSelected();
    this.root.querySelector('[data-action="fit"]').onclick = () => this.fitTimeline();
    this.root.querySelector('[data-action="fitGap"]').onclick = () => this.fitSelectionToNearestGap();
    this.root.querySelector('[data-action="applySegments"]').onclick = () => this.applySegmentCount();
    this.videoAudioToggle.onclick = event => {
      event.stopPropagation();
      this.state.videoAudioEnabled = !this.state.videoAudioEnabled;
      this.sync(); this.render();
      this.setStatus(tr(this.state.videoAudioEnabled ? "audioReferenceOn" : "audioReferenceOff"));
    };
    this.previewPlay.onclick = () => this.togglePreviewPlayback();
    this.previewVideo.onplay = () => { this.previewPlay.textContent = tr("pausePreview"); };
    this.previewVideo.onpause = () => { this.previewPlay.textContent = tr("playPreview"); };
    this.previewVideo.ontimeupdate = () => this.followPreviewPlayback();
    this.previewVideo.onended = () => { this.previewPlay.textContent = tr("playPreview"); };
    for (const input of this.root.querySelectorAll("[data-upload]")) {
      input.onchange = async () => {
        const files = Array.from(input.files || []);
        input.value = "";
        for (const file of files) await this.addFile(input.dataset.upload, file);
      };
    }
    const startInput = this.root.querySelector('[data-field="selectionStart"]');
    const durInput = this.root.querySelector('[data-field="selectionDuration"]');
    const zoomInput = this.root.querySelector('[data-field="zoom"]');
    const segmentCountInput = this.root.querySelector('[data-field="segmentCount"]');
    this.root.addEventListener("input", event => {
      if (event.target === startInput) {
        this.state.selection.start = Math.max(0, num(startInput.value));
        this.playhead = this.state.selection.start;
        this.sync();
      } else if (event.target === durInput) {
        this.state.selection.duration = Math.max(5/24, num(durInput.value, 5));
        this.sync();
      } else if (event.target === segmentCountInput) {
        this.segmentCountDraft=clamp(Math.floor(num(segmentCountInput.value,0)),0,64);
      }
    });
    startInput.onchange = durInput.onchange = () => this.render();
    zoomInput.oninput = () => { this.zoom = num(zoomInput.value, 64); this.renderTimeline(); };
    this.timelinePointerDown = e => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      const target = e.target instanceof Element ? e.target : null;
      const clipElement = target?.closest(".m3td-clip");
      if (clipElement && this.stage.contains(clipElement)) {
        const clip = this.state.videoClips.find(item => String(item.id) === clipElement.dataset.id);
        this.beginClipDrag(e, clip, target?.closest("[data-edge]")?.dataset.edge || "move");
        return;
      }
      const selectionPart = target?.closest(".m3td-selection [data-edge]");
      if (selectionPart && this.stage.contains(selectionPart)) {
        this.beginSelectionDrag(e, selectionPart.dataset.edge || "move");
        return;
      }
      if (target?.closest(".m3td-playhead")) {
        this.beginPlayheadDrag(e);
        return;
      }
      const stageRect = this.stage.getBoundingClientRect();
      const stageScale = stageRect.width / Math.max(1, this.stage.offsetWidth);
      const localY = (e.clientY - stageRect.top) / Math.max(.0001, stageScale);
      const time = this.timeFromClientX(e.clientX);
      const selection = this.state.selection;
      if (localY >= 26 && localY <= 170 && time >= selection.start && time <= selection.start + selection.duration) {
        this.beginSelectionDrag(e, "move");
        return;
      }
      this.beginPlayheadDrag(e);
    };
    // Nodes 2.0 wraps DOM widgets with its own canvas gestures. Capture the
    // press on the timeline so the editing gesture cannot be swallowed.
    this.stage.addEventListener("pointerdown", this.timelinePointerDown, true);
    this.viewport.addEventListener("dblclick", e => {
      if (e.target.closest(".m3td-clip")) return;
      this.fitSelectionToGapAt(this.timeFromClientX(e.clientX));
    });
    this.forwardWheel = event => forwardWheelEvent(event, app.canvas?.canvas);
    this.root.addEventListener("wheel", this.forwardWheel, {passive:false});
  }

  bindExternalFileDrop() {
    const stopComfyDrop = event => {
      if (!isExternalFileDrag(event)) return false;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      return true;
    };
    const showDropTarget = event => {
      if (!stopComfyDrop(event)) return;
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      this.root.dataset.dropLabel = tr("externalDrop");
      this.root.classList.add("external-file-drag");
    };
    const hideDropTarget = event => {
      if (!isExternalFileDrag(event)) return;
      if (event.relatedTarget && this.root.contains(event.relatedTarget)) return;
      stopComfyDrop(event);
      this.root.classList.remove("external-file-drag");
    };
    const receiveFiles = async event => {
      if (!isExternalFileDrag(event)) return;
      const files = Array.from(event.dataTransfer?.files || []);
      stopComfyDrop(event);
      this.root.classList.remove("external-file-drag");
      if (this.uploading) { this.setStatus(tr("uploadBusy")); return; }
      const supported = files.map(file => ({file, kind:uploadKindForFile(file)})).filter(item => item.kind);
      const rejected = files.length - supported.length;
      if (!supported.length) { this.setStatus(tr("unsupportedFile")); return; }
      for (const item of supported) await this.addFile(item.kind, item.file);
      if (rejected) this.setStatus(tr("importedSome", {accepted:supported.length,rejected}));
    };
    this.externalDropHandlers = {showDropTarget, hideDropTarget, receiveFiles};
    this.root.addEventListener("dragenter", showDropTarget, true);
    this.root.addEventListener("dragover", showDropTarget, true);
    this.root.addEventListener("dragleave", hideDropTarget, true);
    this.root.addEventListener("drop", receiveFiles, true);
  }

  timelineDuration() {
    let end = this.state.selection.start + this.state.selection.duration;
    for (const clip of this.state.videoClips) end = Math.max(end, clip.start + clip.duration);
    return Math.max(10, end + 1);
  }

  render() {
    this.root.querySelector('[data-field="selectionStart"]').value = this.state.selection.start.toFixed(2);
    this.root.querySelector('[data-field="selectionDuration"]').value = this.state.selection.duration.toFixed(2);
    this.root.querySelector('[data-field="zoom"]').value = this.zoom;
    this.root.querySelector('[data-field="segmentCount"]').value = this.segmentCountDraft;
    if (this.videoAudioToggle) {
      this.videoAudioToggle.textContent = tr(this.state.videoAudioEnabled ? "off" : "on");
      this.videoAudioToggle.classList.toggle("off", !this.state.videoAudioEnabled);
      this.videoAudioToggle.title = tr(this.state.videoAudioEnabled ? "disableVideoAudio" : "enableVideoAudio");
      this.videoAudioToggle.setAttribute("aria-pressed", String(this.state.videoAudioEnabled));
    }
    this.renderTimeline();
    this.renderInspector();
    this.renderAssets();
    this.renderSegments();
    this.renderTags();
    this.scheduleNodeHeightSync();
  }

  requiredDirectorHeight() {
    const foot = this.root.querySelector(".m3td-foot");
    if (!foot) return DIRECTOR_HEIGHT;
    const contentHeight = Math.ceil(foot.offsetTop + foot.offsetHeight + 2);
    return Math.max(DIRECTOR_HEIGHT, contentHeight);
  }

  scheduleNodeHeightSync() {
    cancelAnimationFrame(this.layoutRAF);
    this.layoutRAF = requestAnimationFrame(() => {
      const desiredHeight = this.requiredDirectorHeight();
      if (this.directorWidget) this.directorWidget.__m3tdHeight = desiredHeight;
      const widgetHost = this.root.closest?.(".dom-widget") || this.root.parentElement;
      if (widgetHost) {
        widgetHost.classList.add("m3td-widget-host");
        widgetHost.style.setProperty("height", `${desiredHeight}px`, "important");
        widgetHost.style.setProperty("min-height", `${desiredHeight}px`, "important");
        widgetHost.style.setProperty("max-height", "none", "important");
        widgetHost.style.setProperty("overflow", "visible", "important");
      }
      const computed = this.node.computeSize?.();
      const currentWidth = this.node.size?.[0] || computed?.[0] || 860;
      const currentHeight = this.node.size?.[1] || 0;
      const computedHeight = Number(computed?.[1]) || 0;
      const chromeCandidate = computedHeight - desiredHeight;
      if (chromeCandidate >= 36 && chromeCandidate <= 600) {
        this.node.__m3tdChromeHeight = chromeCandidate;
      }
      const chromeHeight = Number(this.node.__m3tdChromeHeight) || 120;
      const minimumHeight = Math.ceil(Math.max(computedHeight, desiredHeight + chromeHeight));
      if (Math.abs(currentHeight - minimumHeight) > 1) {
        this.node.setSize?.([currentWidth, minimumHeight]);
      }
      this.node.setDirtyCanvas?.(true, true);
    });
  }

  renderTimeline() {
    const duration = this.timelineDuration();
    const plan = this.referencePlan();
    const width = Math.max(this.viewport?.clientWidth || 500, Math.ceil(duration * this.zoom));
    this.stage.style.width = `${width}px`;
    let html = '<div class="m3td-ruler">';
    const tickStep = this.zoom >= 100 ? .5 : this.zoom >= 48 ? 1 : 2;
    for (let t = 0; t <= duration; t += tickStep) {
      const major = Math.abs(t - Math.round(t)) < .001;
      html += `<i class="m3td-tick ${major ? "major" : ""}" style="left:${t*this.zoom}px">${major ? `<span>${t.toFixed(0)}s</span>` : ""}</i>`;
    }
    html += '</div><div class="m3td-track">';
    for (const clip of this.state.videoClips) html += this.clipHTML(clip, plan);
    html += `</div><div class="m3td-track audio ${this.state.videoAudioEnabled ? "" : "muted"}">`;
    for (const clip of this.state.videoClips) if (clip.hasAudio) html += this.audioClipHTML(clip);
    html += '</div>';
    const sel = this.state.selection;
    html += `<div class="m3td-selection" data-role="selection" style="left:${sel.start*this.zoom}px;width:${Math.max(8,sel.duration*this.zoom)}px"><b class="m3td-sel-move" data-edge="move" title="${esc(tr("moveGenerationRegion"))}">GEN</b><i class="m3td-sel-handle left" data-edge="left" title="${esc(tr("adjustGenerationStart"))}"></i><i class="m3td-sel-handle right" data-edge="right" title="${esc(tr("adjustGenerationEnd"))}"></i></div>`;
    html += `<div class="m3td-snap-guide" style="left:${(this.snapGuide ?? 0)*this.zoom}px;${this.snapGuide == null ? "display:none" : ""}"></div>`;
    html += `<div class="m3td-playhead" data-role="playhead" title="${esc(tr("movePlayhead"))}" style="left:${this.playhead*this.zoom}px"></div>`;
    this.stage.innerHTML = html;
    for (const el of this.stage.querySelectorAll(".m3td-clip")) {
      const clip = this.state.videoClips.find(c => c.id === el.dataset.id);
      const video = el.querySelector("video");
      if (video && clip) video.addEventListener("loadedmetadata", () => { try { video.currentTime = Math.min(clip.trimStart + .05, Math.max(0, video.duration-.05)); } catch (_) {} }, {once:true});
    }
    this.drawWaveforms();
    this.schedulePreviewUpdate();
  }

  clipHTML(clip, plan) {
    const left = clip.start * this.zoom, width = Math.max(10, clip.duration * this.zoom);
    const videoIndex = plan.videoPieces.findIndex(piece => piece.clipId === clip.id);
    const guide = plan.guidePieces.find(piece => piece.clipId === clip.id);
    const mode = clip.referenceMode || "guide";
    const modeTag = guide ? `<span class="m3td-clip-ref ${mode === "boundary" ? "boundary" : "guide"}">${mode === "boundary" ? `EDGE ${esc(tr("frames",{count:guide.frames}))}` : `GUIDE ${esc(tr("frames",{count:guide.frames}))}`}</span>` : (mode === "edit" && videoIndex >= 0 ? `<span class="m3td-clip-ref edit">${esc(tr("editable"))}</span>` : "");
    const refTag = `${videoIndex >= 0 ? `<span class="m3td-clip-ref">&lt;Video ${videoIndex+1}&gt;</span>` : ""}${modeTag}`;
    return `<div class="m3td-clip ${clip.id === this.selectedId ? "selected" : ""}" data-id="${esc(clip.id)}" style="left:${left}px;width:${width}px">
      <video muted preload="metadata" src="${esc(viewURL(clip.file))}"></video><div class="m3td-clip-shade"></div>
      <i class="m3td-handle left" data-edge="left"></i><i class="m3td-handle right" data-edge="right"></i>
      <span class="m3td-clip-name">${esc(clip.name)}</span>${refTag}<span class="m3td-clip-meta">${esc(tr("clipMeta",{duration:clip.duration.toFixed(2),source:clip.trimStart.toFixed(2)}))}</span></div>`;
  }

  audioClipHTML(clip) {
    return `<div class="m3td-audio-clip" style="left:${clip.start*this.zoom}px;width:${Math.max(10,clip.duration*this.zoom)}px"><canvas class="m3td-wave" data-wave="${esc(clip.id)}"></canvas></div>`;
  }

  drawWaveforms() {
    for (const canvas of this.stage.querySelectorAll("canvas[data-wave]")) {
      const clip = this.state.videoClips.find(c => c.id === canvas.dataset.wave);
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * devicePixelRatio)); canvas.height = Math.max(1, Math.floor(rect.height * devicePixelRatio));
      const ctx = canvas.getContext("2d"); ctx.scale(devicePixelRatio, devicePixelRatio); ctx.strokeStyle = "#e3ae58"; ctx.globalAlpha=.8;
      const peaks = clip?.peaks?.length ? clip.peaks : Array.from({length:80}, (_,i) => .18 + Math.abs(Math.sin(i*.47))*.22);
      const h = rect.height, w = rect.width; ctx.beginPath();
      for (let x=0; x<w; x+=2) { const p=peaks[Math.min(peaks.length-1,Math.floor(x/w*peaks.length))]||0; ctx.moveTo(x,h/2-p*h*.45); ctx.lineTo(x,h/2+p*h*.45); }
      ctx.stroke();
    }
  }

  clipAtPlayhead() {
    const epsilon = 1 / 48;
    const matches = this.state.videoClips.filter(clip =>
      this.playhead >= clip.start - epsilon && this.playhead <= clip.start + clip.duration + epsilon
    );
    return matches.find(clip => clip.id === this.selectedId) || matches[matches.length - 1] || null;
  }

  previewSourceTime(clip) {
    return clamp(clip.trimStart + this.playhead - clip.start, clip.trimStart, clip.trimStart + clip.duration);
  }

  formatPreviewTime(seconds) {
    const safe = Math.max(0, num(seconds));
    const minutes = Math.floor(safe / 60);
    const rest = safe - minutes * 60;
    return `${String(minutes).padStart(2,"0")}:${rest.toFixed(2).padStart(5,"0")}`;
  }

  schedulePreviewUpdate(forceSeek = false) {
    cancelAnimationFrame(this.previewRAF);
    this.previewRAF = requestAnimationFrame(() => this.updatePreview(forceSeek));
  }

  async ensurePreviewProxy(clip) {
    if (clip.proxy) return clip.proxy;
    if (this.proxyRequests.has(clip.id)) return this.proxyRequests.get(clip.id);
    const request = (async () => {
      this.previewEmpty.textContent = tr("proxyGenerating");
      this.setStatus(tr("proxyGeneratingStatus",{name:clip.name}));
      const response = await api.fetchApi("/minimax_h3_timeline/preview_proxy", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({filename:clip.file}),
      });
      const payload = await responseJSON(response);
      if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
      clip.proxy = payload.proxy;
      this.sync();
      this.setStatus(tr("proxyReady",{name:clip.name}));
      return clip.proxy;
    })().catch(error => {
      console.error("[MiniMaxH3TimelineDirector] preview proxy", error);
      this.previewEmpty.textContent = tr("proxyFailed",{error:error.message});
      this.setStatus(tr("previewFailed",{error:error.message}));
      throw error;
    }).finally(() => this.proxyRequests.delete(clip.id));
    this.proxyRequests.set(clip.id, request);
    return request;
  }

  async updatePreview(forceSeek = false) {
    const clip = this.clipAtPlayhead();
    if (!clip) {
      this.previewVideo.pause();
      this.previewVideo.style.display = "none";
      this.previewEmpty.style.display = "block";
      this.previewEmpty.textContent = tr("noClipAtPlayhead");
      this.previewName.textContent = tr("noPreviewVideo");
      this.previewTime.textContent = this.formatPreviewTime(this.playhead);
      this.previewClipId = null;
      return;
    }
    const sourceTime = this.previewSourceTime(clip);
    this.previewTime.textContent = tr("timelineAndSourceTime",{timeline:this.formatPreviewTime(this.playhead),source:this.formatPreviewTime(sourceTime)});
    this.previewName.textContent = clip.name;
    if (!clip.proxy) {
      this.previewVideo.style.display = "none";
      this.previewEmpty.style.display = "block";
      this.ensurePreviewProxy(clip).then(() => this.schedulePreviewUpdate(true)).catch(() => {});
      return;
    }
    const proxyURL = viewURL(clip.proxy);
    if (this.previewVideo.dataset.proxy !== clip.proxy) {
      this.previewVideo.pause();
      this.previewVideo.dataset.proxy = clip.proxy;
      this.previewVideo.src = proxyURL;
      this.previewVideo.load();
      this.previewClipId = clip.id;
      forceSeek = true;
    }
    if (this.previewClipId !== clip.id) forceSeek = true;
    this.previewClipId = clip.id;
    this.previewVideo.style.display = "block";
    this.previewEmpty.style.display = "none";
    if (forceSeek || this.previewVideo.paused) {
      const seek = () => {
        if (Number.isFinite(this.previewVideo.duration)) {
          this.previewVideo.currentTime = clamp(sourceTime, 0, Math.max(0, this.previewVideo.duration - .01));
        }
      };
      if (this.previewVideo.readyState >= 1) seek();
      else this.previewVideo.addEventListener("loadedmetadata", seek, {once:true});
    }
  }

  async togglePreviewPlayback() {
    if (!this.previewVideo.paused) { this.previewVideo.pause(); return; }
    const clip = this.clipAtPlayhead();
    if (!clip) { this.setStatus(tr("movePlayheadFirst")); return; }
    try {
      await this.ensurePreviewProxy(clip);
      await this.updatePreview(true);
      if (this.previewVideo.readyState < 1) {
        await new Promise(resolve => this.previewVideo.addEventListener("loadedmetadata", resolve, {once:true}));
      }
      this.previewVideo.currentTime = clamp(this.previewSourceTime(clip), 0, Math.max(0, this.previewVideo.duration - .01));
      await this.previewVideo.play();
    } catch (error) {
      this.setStatus(tr("previewFailed",{error:error.message}));
    }
  }

  followPreviewPlayback() {
    if (this.previewVideo.paused || !this.previewClipId) return;
    const clip = this.state.videoClips.find(item => item.id === this.previewClipId);
    if (!clip) { this.previewVideo.pause(); return; }
    const sourceEnd = clip.trimStart + clip.duration;
    if (this.previewVideo.currentTime >= sourceEnd - 1 / 24) {
      this.playhead = clip.start + clip.duration;
      this.previewVideo.pause();
    } else {
      this.playhead = clamp(clip.start + this.previewVideo.currentTime - clip.trimStart, clip.start, clip.start + clip.duration);
    }
    this.previewTime.textContent = tr("timelineAndSourceTime",{timeline:this.formatPreviewTime(this.playhead),source:this.formatPreviewTime(this.previewVideo.currentTime)});
    this.scheduleDragVisualUpdate();
  }

  beginClipDrag(event, clip, mode) {
    if (!clip) return;
    this.preparePointerDrag(event);
    this.previewVideo.pause();
    this.selectedId = clip.id;
    const rect = this.stage.getBoundingClientRect();
    const canvasScale = rect.width / Math.max(1, this.stage.offsetWidth);
    this.drag = { kind:"clip", mode, x:event.clientX, scale:canvasScale, start:clip.start, duration:clip.duration, trimStart:clip.trimStart, clip };
    for (const element of this.stage.querySelectorAll(".m3td-clip")) {
      element.classList.toggle("selected", element.dataset.id === clip.id);
    }
    this.renderInspector();
    this.scheduleNodeHeightSync();
  }

  beginSelectionDrag(event, mode) {
    this.preparePointerDrag(event);
    this.previewVideo.pause();
    const rect = this.stage.getBoundingClientRect();
    const canvasScale = rect.width / Math.max(1, this.stage.offsetWidth);
    this.drag = { kind:"selection", mode, x:event.clientX, scale:canvasScale, start:this.state.selection.start, duration:this.state.selection.duration };
  }

  beginPlayheadDrag(event) {
    this.preparePointerDrag(event);
    this.previewVideo.pause();
    const snapped = this.snapValue(this.timeFromClientX(event.clientX), this.snapPoints(null, true));
    this.playhead = snapped.value;
    this.snapGuide = snapped.snapAt;
    this.drag = {kind:"playhead"};
    this.scheduleDragVisualUpdate();
  }

  selectHostNode() {
    const canvas = app.canvas;
    try {
      if (typeof canvas?.selectNode === "function") canvas.selectNode(this.node, false);
      else if (typeof canvas?.selectNodes === "function") canvas.selectNodes([this.node]);
    } catch (_) { /* Selection must never block timeline editing. */ }
    canvas?.setDirty?.(true, true);
    this.node.setDirtyCanvas?.(true, true);
  }

  preparePointerDrag(event) {
    event.preventDefault();
    event.stopPropagation();
    this.selectHostNode();
    this.dragPointerId = event.pointerId;
    try { this.stage.setPointerCapture?.(event.pointerId); } catch (_) {}
  }

  scheduleDragVisualUpdate() {
    if (this.dragRAF) return;
    this.dragRAF = requestAnimationFrame(() => {
      this.dragRAF = 0;
      this.updateDragVisuals();
    });
  }

  updateDragVisuals() {
    const selection = this.stage.querySelector(".m3td-selection");
    if (selection) {
      selection.style.left = `${this.state.selection.start * this.zoom}px`;
      selection.style.width = `${Math.max(8, this.state.selection.duration * this.zoom)}px`;
    }
    const playhead = this.stage.querySelector(".m3td-playhead");
    if (playhead) playhead.style.left = `${this.playhead * this.zoom}px`;
    const snap = this.stage.querySelector(".m3td-snap-guide");
    if (snap) {
      snap.style.display = this.snapGuide == null ? "none" : "block";
      if (this.snapGuide != null) snap.style.left = `${this.snapGuide * this.zoom}px`;
    }
    const startInput = this.root.querySelector('[data-field="selectionStart"]');
    const durationInput = this.root.querySelector('[data-field="selectionDuration"]');
    if (startInput) startInput.value = this.state.selection.start.toFixed(2);
    if (durationInput) durationInput.value = this.state.selection.duration.toFixed(2);

    const clip = this.drag?.kind === "clip" ? this.drag.clip : null;
    if (clip) {
      const clipElement = Array.from(this.stage.querySelectorAll(".m3td-clip"))
        .find(element => element.dataset.id === String(clip.id));
      if (clipElement) {
        clipElement.style.left = `${clip.start * this.zoom}px`;
        clipElement.style.width = `${Math.max(10, clip.duration * this.zoom)}px`;
        const meta = clipElement.querySelector(".m3td-clip-meta");
        if (meta) meta.textContent = tr("clipMeta",{duration:clip.duration.toFixed(2),source:clip.trimStart.toFixed(2)});
      }
      const wave = Array.from(this.stage.querySelectorAll("canvas[data-wave]"))
        .find(element => element.dataset.wave === String(clip.id));
      const audioElement = wave?.closest(".m3td-audio-clip");
      if (audioElement) {
        audioElement.style.left = `${clip.start * this.zoom}px`;
        audioElement.style.width = `${Math.max(10, clip.duration * this.zoom)}px`;
      }
      for (const input of this.inspector.querySelectorAll("input[data-edit]")) {
        if (input.dataset.edit === "start") input.value = clip.start.toFixed(2);
        if (input.dataset.edit === "trimStart") input.value = clip.trimStart.toFixed(2);
        if (input.dataset.edit === "duration") input.value = clip.duration.toFixed(2);
      }
    }
    if (this.drag?.kind === "playhead") this.schedulePreviewUpdate();
  }

  attachGlobalPointerHandlers() {
    this.pointerMove = e => {
      if (!this.drag) return;
      if (this.dragPointerId != null && e.pointerId !== this.dragPointerId) return;
      e.preventDefault();
      e.stopPropagation();
      if (this.drag.kind === "playhead") {
        const snapped = this.snapValue(this.timeFromClientX(e.clientX), this.snapPoints(null, true));
        this.playhead = snapped.value; this.snapGuide = snapped.snapAt; this.scheduleDragVisualUpdate(); return;
      }
      const delta = (e.clientX - this.drag.x) / (this.zoom * (this.drag.scale || 1));
      if (this.drag.kind === "selection") {
        const points = this.snapPoints(null, false);
        if (this.drag.mode === "move") {
          const snapped = this.snapInterval(this.drag.start + delta, this.drag.duration, points);
          this.state.selection.start = snapped.start; this.snapGuide = snapped.snapAt;
        }
        else if (this.drag.mode === "left") {
          const end = this.drag.start + this.drag.duration;
          const snapped = this.snapValue(clamp(this.drag.start + delta, 0, end - 5/24), points);
          const start = clamp(snapped.value, 0, end - 5/24); this.snapGuide = snapped.snapAt;
          this.state.selection.start = start; this.state.selection.duration = end - start;
        } else {
          const proposedEnd = this.drag.start + Math.max(5/24, this.drag.duration + delta);
          const snapped = this.snapValue(proposedEnd, points);
          this.state.selection.duration = Math.max(5/24, snapped.value - this.drag.start); this.snapGuide = snapped.snapAt;
        }
      } else {
        const clip = this.drag.clip;
        const points = this.snapPoints(clip.id, true);
        if (this.drag.mode === "move") {
          const snapped = this.snapInterval(this.drag.start + delta, this.drag.duration, points);
          clip.start = snapped.start; this.snapGuide = snapped.snapAt;
        }
        else if (this.drag.mode === "left") {
          const end = this.drag.start + this.drag.duration;
          const maxTrim = this.drag.trimStart + this.drag.duration - 5/24;
          const snapped = this.snapValue(clamp(this.drag.start + delta, 0, end - 5/24), points);
          const newStart = clamp(snapped.value, 0, end - 5/24); this.snapGuide = snapped.snapAt;
          const applied = newStart - this.drag.start;
          clip.start = newStart; clip.duration = end - newStart; clip.trimStart = clamp(this.drag.trimStart + applied, 0, maxTrim);
        } else {
          const available = Math.max(5/24, clip.sourceDuration - this.drag.trimStart);
          const proposedEnd = this.drag.start + clamp(this.drag.duration + delta, 5/24, available);
          const snapped = this.snapValue(proposedEnd, points);
          clip.duration = clamp(snapped.value - this.drag.start, 5/24, available); this.snapGuide = snapped.snapAt;
        }
      }
      this.scheduleDragVisualUpdate();
    };
    this.pointerUp = e => {
      if (!this.drag) return;
      if (this.dragPointerId != null && e?.pointerId != null && e.pointerId !== this.dragPointerId) return;
      e?.preventDefault?.();
      e?.stopPropagation?.();
      if (this.dragRAF) {
        cancelAnimationFrame(this.dragRAF);
        this.dragRAF = 0;
        this.updateDragVisuals();
      }
      this.drag = null;
      const pointerId = this.dragPointerId;
      this.dragPointerId = null;
      try { if (pointerId != null && this.stage.hasPointerCapture?.(pointerId)) this.stage.releasePointerCapture(pointerId); } catch (_) {}
      this.snapGuide = null;
      this.sync();
      this.render();
    };
    window.addEventListener("pointermove", this.pointerMove, true);
    window.addEventListener("pointerup", this.pointerUp, true);
    window.addEventListener("pointercancel", this.pointerUp, true);
  }

  renderInspector() {
    const clip = this.state.videoClips.find(c => c.id === this.selectedId);
    if (!clip) { this.inspector.innerHTML = `<span>${esc(tr("noClipInspector"))}</span>`; return; }
    this.inspector.innerHTML = `<strong title="${esc(clip.name)}">${esc(clip.name)}</strong>
      <label class="m3td-field">${esc(tr("start"))} <input data-edit="start" type="number" min="0" step="0.04" value="${clip.start.toFixed(2)}"></label>
      <label class="m3td-field">${esc(tr("sourceIn"))} <input data-edit="trimStart" type="number" min="0" step="0.04" value="${clip.trimStart.toFixed(2)}"></label>
      <label class="m3td-field">${esc(tr("clipDuration"))} <input data-edit="duration" type="number" min="0.21" step="0.04" value="${clip.duration.toFixed(2)}"></label>
      <label class="m3td-field">${esc(tr("videoPurpose"))} <select data-mode><option value="guide" ${clip.referenceMode === "guide" ? "selected" : ""}>${esc(tr("fixedGuide"))}</option><option value="edit" ${clip.referenceMode === "edit" ? "selected" : ""}>${esc(tr("editableReference"))}</option><option value="boundary" ${clip.referenceMode === "boundary" ? "selected" : ""}>${esc(tr("boundaryOnly"))}</option></select></label>
      <span>${esc(clip.hasAudio ? tr(this.state.videoAudioEnabled ? "sourceAudioOn" : "sourceAudioOff") : tr("noSourceAudio"))}</span>`;
    for (const input of this.inspector.querySelectorAll("input[data-edit]")) input.onchange = () => {
      const key=input.dataset.edit, value=Math.max(0,num(input.value));
      if (key === "duration") clip.duration=clamp(value,5/24,Math.max(5/24,clip.sourceDuration-clip.trimStart));
      else if (key === "trimStart") { clip.trimStart=clamp(value,0,Math.max(0,clip.sourceDuration-5/24)); clip.duration=Math.min(clip.duration,clip.sourceDuration-clip.trimStart); }
      else clip.start=value;
      this.sync(); this.render();
    };
    this.inspector.querySelector("select[data-mode]").onchange = event => {
      clip.referenceMode=event.target.value;
      this.setStatus(tr(clip.referenceMode === "edit" ? "editableModeStatus" : (clip.referenceMode === "boundary" ? "boundaryModeStatus" : "fixedGuideStatus")));
      this.sync();this.render();
    };
  }

  renderAssets() {
    const imageBin = this.root.querySelector('[data-bin="images"]');
    const audioBin = this.root.querySelector('[data-bin="audios"]');
    this.root.querySelectorAll(".m3td-bin-title span:first-child")[0].textContent = tr("independentImages",{count:this.state.images.length});
    this.root.querySelectorAll(".m3td-bin-title span:first-child")[1].textContent = tr("independentAudio",{count:this.state.audios.length});
    imageBin.innerHTML = this.state.images.map((a,i) => `<div class="m3td-asset" draggable="true" data-asset-id="${esc(a.id)}" data-asset-kind="images" title="${esc(tr("dragReorder"))}"><img draggable="false" src="${esc(viewURL(a.file))}"><span class="m3td-asset-tag">&lt;Picture ${i+1}&gt;</span><span class="m3td-asset-name">${esc(a.name)}</span><button draggable="false" class="m3td-asset-x" data-remove-image="${esc(a.id)}">×</button></div>`).join("");
    audioBin.innerHTML = this.state.audios.map((a,i) => `<div class="m3td-asset audio" draggable="true" data-asset-id="${esc(a.id)}" data-asset-kind="audios" title="${esc(tr("dragReorder"))}"><span class="m3td-asset-tag">&lt;Audio ${i+1}&gt;</span><span class="m3td-asset-name">${esc(a.name)}</span><button draggable="false" class="m3td-asset-x" data-remove-audio="${esc(a.id)}">×</button></div>`).join("");
    for (const b of imageBin.querySelectorAll("[data-remove-image]")) b.onclick=e=>{e.stopPropagation();this.state.images=this.state.images.filter(a=>a.id!==b.dataset.removeImage);this.pruneSegmentAssignments();this.sync();this.render();};
    for (const b of audioBin.querySelectorAll("[data-remove-audio]")) b.onclick=e=>{e.stopPropagation();this.state.audios=this.state.audios.filter(a=>a.id!==b.dataset.removeAudio);this.pruneSegmentAssignments();this.sync();this.render();};
    this.bindAssetReorder(imageBin,"images","imageOrderUpdated");
    this.bindAssetReorder(audioBin,"audios","audioOrderUpdated");
  }

  bindAssetReorder(bin, kind, label) {
    const clearMarkers=()=>{for(const card of bin.querySelectorAll(".m3td-asset"))card.classList.remove("dragging","drop-before","drop-after");};
    for(const card of bin.querySelectorAll(".m3td-asset")){
      card.ondragstart=e=>{
        if(e.target.closest?.("button")){e.preventDefault();return;}
        this.assetDrag={kind,id:card.dataset.assetId,source:"library"};card.classList.add("dragging");
        // Library cards are moved when reordered inside the library, but copied
        // when assigned to one or more prompt segments.  `move` alone makes a
        // segment's `dropEffect = "copy"` invalid, so Chromium shows drag-over
        // feedback yet cancels the final drop.
        e.dataTransfer.effectAllowed="copyMove";e.dataTransfer.setData("text/plain",card.dataset.assetId);
      };
      card.ondragover=e=>{
        if(!this.assetDrag||this.assetDrag.kind!==kind||this.assetDrag.id===card.dataset.assetId)return;
        e.preventDefault();e.dataTransfer.dropEffect="move";
        const rect=card.getBoundingClientRect(),after=e.clientX>=rect.left+rect.width/2;
        for(const other of bin.querySelectorAll(".m3td-asset"))other.classList.remove("drop-before","drop-after");
        card.classList.add(after?"drop-after":"drop-before");
      };
      card.ondrop=e=>{
        if(!this.assetDrag||this.assetDrag.kind!==kind)return;
        e.preventDefault();const rect=card.getBoundingClientRect(),after=e.clientX>=rect.left+rect.width/2;
        const changed=reorderById(this.state[kind],this.assetDrag.id,card.dataset.assetId,after);
        this.assetDrag=null;clearMarkers();
        if(changed){this.sync();this.render();this.setStatus(tr(label));}
      };
      card.ondragend=()=>{this.assetDrag=null;clearMarkers();};
    }
  }

  applySegmentCount() {
    const count=clamp(Math.floor(num(this.segmentCountDraft,0)),0,64);
    const previous=Array.isArray(this.state.segmentConfig?.segments)?this.state.segmentConfig.segments:[];
    this.state.segmentConfig={count,segments:Array.from({length:count},(_,index)=>({
      images:[...(previous[index]?.images||[])],
      audios:[...(previous[index]?.audios||[])],
    }))};
    this.segmentCountDraft=count;
    this.pruneSegmentAssignments();
    this.sync();this.render();
    this.setStatus(count?tr("segmentsCreated",{count}):tr("segmentsDisabled"));
  }

  pruneSegmentAssignments() {
    const imageIds=new Set(this.state.images.map(item=>String(item.id)));
    const audioIds=new Set(this.state.audios.map(item=>String(item.id)));
    for(const segment of this.state.segmentConfig?.segments||[]){
      segment.images=normalizedAssetIds(segment.images,imageIds);
      segment.audios=normalizedAssetIds(segment.audios,audioIds);
    }
  }

  segmentAssetHTML(kind,id,localIndex,segmentIndex) {
    const asset=this.state[kind].find(item=>String(item.id)===String(id));
    if(!asset)return "";
    const isImage=kind==="images";
    return `<div class="m3td-asset ${isImage?"":"audio"}" draggable="true" data-segment-asset="${esc(id)}" data-segment-kind="${kind}" data-segment-index="${segmentIndex}" title="${esc(tr("segmentAssetTitle"))}">
      ${isImage?`<img draggable="false" src="${esc(viewURL(asset.file))}">`:""}
      <span class="m3td-asset-tag">&lt;${isImage?"Picture":"Audio"} ${localIndex+1}&gt;</span>
      <span class="m3td-asset-name">${esc(asset.name)}</span>
      <button draggable="false" class="m3td-asset-x" data-remove-segment-asset="${esc(id)}">×</button></div>`;
  }

  renderSegments() {
    const section=this.root.querySelector(".m3td-segments"),list=this.root.querySelector(".m3td-segment-list");
    const count=this.state.segmentConfig?.count||0;
    section.hidden=count<=0;
    if(count<=0){list.innerHTML="";return;}
    list.innerHTML=this.state.segmentConfig.segments.map((segment,index)=>`<section class="m3td-segment" data-segment="${index}">
      <div class="m3td-segment-title"><strong>${esc(tr("segmentTitle",{index:index+1}))}</strong><span>${esc(tr("segmentPromptMatch",{index:index+1}))}</span></div>
      <div class="m3td-segment-bins">
        <div class="m3td-segment-bin" data-segment-drop="images" data-segment-index="${index}"><label class="m3td-segment-bin-label">${esc(tr("segmentImages"))}</label><div class="m3td-segment-bin-list">${segment.images.map((id,i)=>this.segmentAssetHTML("images",id,i,index)).join("")}</div></div>
        <div class="m3td-segment-bin" data-segment-drop="audios" data-segment-index="${index}"><label class="m3td-segment-bin-label">${esc(tr("segmentAudio"))}</label><div class="m3td-segment-bin-list">${segment.audios.map((id,i)=>this.segmentAssetHTML("audios",id,i,index)).join("")}</div></div>
      </div></section>`).join("");
    for(const button of list.querySelectorAll("[data-remove-segment-asset]"))button.onclick=event=>{
      event.stopPropagation();
      const card=button.closest("[data-segment-asset]"),segment=this.state.segmentConfig.segments[num(card.dataset.segmentIndex)];
      segment[card.dataset.segmentKind]=segment[card.dataset.segmentKind].filter(id=>String(id)!==String(card.dataset.segmentAsset));
      this.sync();this.render();
    };
    const clear=()=>{for(const item of list.querySelectorAll(".drag-over,.drop-before,.drop-after,.dragging"))item.classList.remove("drag-over","drop-before","drop-after","dragging");};
    const place=(kind,segmentIndex,targetId=null,after=true)=>{
      if(!this.assetDrag||this.assetDrag.kind!==kind)return false;
      const segment=this.state.segmentConfig.segments[segmentIndex];if(!segment)return false;
      let values=segment[kind].filter(id=>String(id)!==String(this.assetDrag.id));
      if(targetId==null)values.push(this.assetDrag.id);
      else {const at=values.findIndex(id=>String(id)===String(targetId));values.splice(at<0?values.length:at+(after?1:0),0,this.assetDrag.id);}
      segment[kind]=values;return true;
    };
    for(const bin of list.querySelectorAll("[data-segment-drop]")){
      const kind=bin.dataset.segmentDrop,index=num(bin.dataset.segmentIndex);
      bin.ondragover=event=>{if(!this.assetDrag||this.assetDrag.kind!==kind)return;event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect=this.assetDrag.source==="library"?"copy":"move";bin.classList.add("drag-over");};
      bin.ondragleave=event=>{if(!bin.contains(event.relatedTarget))bin.classList.remove("drag-over");};
      bin.ondrop=event=>{if(!this.assetDrag||this.assetDrag.kind!==kind)return;event.preventDefault();event.stopPropagation();if(event.target.closest?.("[data-segment-asset]"))return;if(place(kind,index)){this.assetDrag=null;clear();this.sync();this.render();this.setStatus(tr("segmentUpdated",{index:index+1}));}};
    }
    for(const card of list.querySelectorAll("[data-segment-asset]")){
      const kind=card.dataset.segmentKind,index=num(card.dataset.segmentIndex),id=card.dataset.segmentAsset;
      card.ondragstart=event=>{if(event.target.closest?.("button")){event.preventDefault();return;}this.assetDrag={kind,id,source:"segment",segmentIndex:index};card.classList.add("dragging");event.dataTransfer.effectAllowed="copyMove";event.dataTransfer.setData("text/plain",id);};
      card.ondragover=event=>{if(!this.assetDrag||this.assetDrag.kind!==kind||this.assetDrag.id===id)return;event.preventDefault();event.stopPropagation();const rect=card.getBoundingClientRect(),after=event.clientX>=rect.left+rect.width/2;for(const other of card.parentElement.querySelectorAll("[data-segment-asset]"))other.classList.remove("drop-before","drop-after");card.classList.add(after?"drop-after":"drop-before");};
      card.ondrop=event=>{if(!this.assetDrag||this.assetDrag.kind!==kind)return;event.preventDefault();event.stopPropagation();const rect=card.getBoundingClientRect(),after=event.clientX>=rect.left+rect.width/2;if(place(kind,index,id,after)){this.assetDrag=null;clear();this.sync();this.render();this.setStatus(tr("segmentOrderUpdated",{index:index+1}));}};
      card.ondragend=()=>{this.assetDrag=null;clear();};
    }
  }

  renderTags() {
    const plan=this.referencePlan();
    const independentPictures=this.state.images.length;
    const videoText=plan.videoPieces.length ? tr("normalVideoRefs",{count:plan.videoPieces.length}) : tr("noNormalVideoRefs");
    const audioTotal=plan.pairedAudioCount+this.state.audios.length;
    const pictureText=independentPictures ? tr("independentPictures",{count:independentPictures}) : tr("noIndependentPictures");
    const guideFrames=plan.guidePieces.reduce((sum,item)=>sum+item.frames,0);
    const fullGuides=plan.guidePieces.filter(item=>item.mode==="guide").length;
    const edgeGuides=plan.guidePieces.filter(item=>item.mode==="boundary").length;
    const guideParts=[fullGuides?tr("nativeFixed",{count:fullGuides}):"",edgeGuides?tr("boundaryFixed",{count:edgeGuides}):""].filter(Boolean).join(" + ");
    const guideText=plan.guidePieces.length ? tr("guideSummary",{parts:guideParts,frames:guideFrames}) : (plan.gapGuideCount ? tr("gapGuide",{count:plan.gapGuideCount}) : tr("noFixedGuide"));
    const standaloneAudio=this.state.audios.length ? tr("standaloneAudioRefs",{count:this.state.audios.length}) : tr("noStandaloneAudio");
    const pairedAudio=!this.state.videoAudioEnabled ? tr("videoAudioDisabled") : (plan.pairedAudioCount ? tr("pairedVideoAudio",{start:this.state.audios.length+1,end:audioTotal}) : tr("noVideoAudioLabels"));
    const segmentText=this.state.segmentConfig.count?tr("segmentFilterSummary",{count:this.state.segmentConfig.count}):tr("noSegmentFilter");
    this.root.querySelector(".m3td-tags").textContent = `${segmentText} · ${pictureText} · ${guideText} · ${videoText} · ${standaloneAudio} · ${pairedAudio}`;
  }

  splitSelected() {
    const index=this.state.videoClips.findIndex(c=>c.id===this.selectedId); if(index<0)return;
    const clip=this.state.videoClips[index], cut=this.playhead-clip.start;
    if(cut<=5/24 || cut>=clip.duration-5/24){this.setStatus(tr("playheadInsideClip"));return;}
    const right={...clip,id:uid(),start:this.playhead,duration:clip.duration-cut,trimStart:clip.trimStart+cut};
    clip.duration=cut; this.state.videoClips.splice(index+1,0,right); this.selectedId=right.id; this.sync();this.render();
  }

  deleteSelected() {
    if(!this.selectedId)return; this.state.videoClips=this.state.videoClips.filter(c=>c.id!==this.selectedId);this.selectedId=null;this.sync();this.render();
  }

  fitTimeline() {
    const duration=this.timelineDuration(), available=Math.max(300,this.viewport.clientWidth-10);this.zoom=clamp(available/duration,24,180);this.render();
  }

  fitSelectionToGapAt(time) {
    const gaps=this.timelineGaps();
    if(!gaps.length){this.setStatus(tr("noMatchingGap"));return;}
    const gap=gaps.reduce((best,current)=>{
      const distance=time<current.start?current.start-time:time>current.start+current.duration?time-current.start-current.duration:0;
      const bestDistance=time<best.start?best.start-time:time>best.start+best.duration?time-best.start-best.duration:0;
      return distance<bestDistance?current:best;
    });
    this.state.selection.start=gap.start;this.state.selection.duration=gap.duration;this.playhead=gap.start;
    this.sync();this.render();this.setStatus(tr("selectionMatchedGap",{duration:gap.duration.toFixed(2)}));
  }

  fitSelectionToNearestGap() {
    const anchor=this.state.selection.start+this.state.selection.duration/2;
    this.fitSelectionToGapAt(anchor);
  }

  setStatus(message, progress=null) { this.status.textContent=message; if(progress!=null)this.progress.style.width=`${clamp(progress,0,1)*100}%`; }

  async addFile(kind,file) {
    if(this.uploading)return;
    if(kind==="image"&&this.state.images.length>=9){this.setStatus(tr("maxImages"));return;}
    if(kind==="audio"&&this.state.audios.length>=3){this.setStatus(tr("maxAudio"));return;}
    this.uploading=true;
    try{
      if(file.size<=0)throw new Error(tr("emptyFile"));
      if(file.size>MAX_UPLOAD_BYTES)throw new Error(tr("tooLarge"));
      const serverName=`${Date.now()}_${Math.random().toString(36).slice(2,7)}_${file.name.replace(/[^\w.()\-\u4e00-\u9fff]+/gu,"_")}`;
      const data=new FormData();
      data.append("image",file,serverName);
      data.append("type","input");
      data.append("subfolder",UPLOAD_SUBFOLDER);
      this.setStatus(tr("uploading",{name:file.name}),0.15);
      const uploadResponse=await api.fetchApi("/upload/image",{method:"POST",body:data});
      const uploadPayload=await responseJSON(uploadResponse);
      if(!uploadResponse.ok){
        const hint=uploadResponse.status===413?tr("uploadSizeHint"):"";
        throw new Error(uploadPayload.error||tr("uploadFailed",{status:uploadResponse.status,hint}));
      }
      const uploadedFile=uploadedRelativePath(uploadPayload);
      this.setStatus(tr("checking",{name:file.name}),0.75);
      const infoResponse=await api.fetchApi("/minimax_h3_timeline/media_info",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({filename:uploadedFile,kind}),
      });
      const info=await responseJSON(infoResponse);
      if(!infoResponse.ok||info.error)throw new Error(info.error||tr("mediaCheckFailed",{status:infoResponse.status}));
      if(kind==="video"){
        if(!info.hasVideo)throw new Error(tr("noVideoTrack"));
        const start=this.state.videoClips.reduce((m,c)=>Math.max(m,c.start+c.duration),0);
        const duration=Math.max(5/24,num(info.duration,5));
        const clip={id:uid(),file:info.filename,name:file.name,start,duration,trimStart:0,sourceDuration:duration,hasAudio:!!info.hasAudio,referenceMode:"guide",peaks:info.peaks||[],proxy:""};
        this.state.videoClips.push(clip);this.selectedId=clip.id;
      }else if(kind==="image")this.state.images.push({id:uid(),file:info.filename,name:file.name,width:info.width||0,height:info.height||0});
      else { if(!info.hasAudio)throw new Error(tr("noAudioTrack")); this.state.audios.push({id:uid(),file:info.filename,name:file.name,duration:info.duration||0,trimStart:0}); }
      this.sync();this.render();this.setStatus(tr("addedFile",{name:file.name}),1);
    }catch(error){console.error("[MiniMaxH3TimelineDirector]",error);this.setStatus(tr("failed",{error:error.message}),0);}
    finally{this.uploading=false;setTimeout(()=>{this.progress.style.width="0";},800);}
  }

  reload() { this.previewVideo?.pause();this.state=normalizeState(this.readWidget());this.segmentCountDraft=this.state.segmentConfig.count;this.selectedId=null;this.playhead=this.state.selection.start;this.previewClipId=null;this.bindGenerationWidget();this.syncGenerationWidget();this.render(); }
  destroy() {
    cancelAnimationFrame(this.previewRAF);cancelAnimationFrame(this.dragRAF);cancelAnimationFrame(this.layoutRAF);this.contentResizeObserver?.disconnect();this.previewVideo?.pause();window.removeEventListener("pointermove",this.pointerMove,true);window.removeEventListener("pointerup",this.pointerUp,true);window.removeEventListener("pointercancel",this.pointerUp,true);
    this.stage?.removeEventListener("pointerdown",this.timelinePointerDown,true);
    this.root.removeEventListener("wheel",this.forwardWheel);
    if(this.externalDropHandlers){
      this.root.removeEventListener("dragenter",this.externalDropHandlers.showDropTarget,true);
      this.root.removeEventListener("dragover",this.externalDropHandlers.showDropTarget,true);
      this.root.removeEventListener("dragleave",this.externalDropHandlers.hideDropTarget,true);
      this.root.removeEventListener("drop",this.externalDropHandlers.receiveFiles,true);
    }
  }
}

app.registerExtension({
  name: "MiniMaxH3.TimelineDirector",
  async beforeRegisterNodeDef(nodeType,nodeData) {
    if(nodeData.name==="MiniMaxH3FiniteSegmentSampler"){
      const originalConfigure=nodeType.prototype.onConfigure;
      nodeType.prototype.onConfigure=function(info){
        const result=originalConfigure?.apply(this,arguments);
        const legacy=Array.isArray(info?.widgets_values)&&info.widgets_values.length>=5?info.widgets_values:null;
        const named=info?.widgets_values_named;
        const values={
          seed:named?.seed??legacy?.[0],
          continue_audio_latent:named?.continue_audio_latent??legacy?.[2],
          ref_image_size:named?.ref_image_size??legacy?.[4],
        };
        for(const [name,value] of Object.entries(values)){
          const widget=this.widgets?.find(item=>item.name===name);
          if(widget&&value!==undefined)widget.value=value;
        }
        return result;
      };
      return;
    }
    if(!TIMELINE_NODE_NAMES.has(nodeData.name))return;
    await ensureTimelineLocale();
    installStyles();
    const originalCreated=nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated=function(){
      const result=originalCreated?.apply(this,arguments);
      const timelineWidget=this.widgets?.find(w=>w.name==="timeline_data");
      if(timelineWidget){
        timelineWidget.type="hidden"; timelineWidget.computeSize=()=>[0,-4];
        // Modern ComfyUI may recreate/reset DOM widget wrappers while a node is
        // resized.  Hiding the textarea only once therefore leaves an invisible
        // full-node overlay which still intercepts canvas drags.  Keep a small
        // idempotent hider on the node and run it after every relevant lifecycle
        // event.  Hide the real `.dom-widget` host, not its canvas transform
        // parent (`.isolate`).
        this.__m3tdHideTimelineWidget=()=>{
          const timelineElement=timelineWidget.element || timelineWidget.inputEl;
          if(!timelineElement)return false;
          const timelineHost=timelineElement.closest?.(".dom-widget") || timelineElement.parentElement;
          timelineElement.style.setProperty("display","none","important");
          timelineElement.style.setProperty("pointer-events","none","important");
          if(timelineHost){
            timelineHost.style.setProperty("display","none","important");
            timelineHost.style.setProperty("pointer-events","none","important");
            timelineHost.style.setProperty("height","0px","important");
            timelineHost.style.setProperty("min-height","0px","important");
          }
          return true;
        };
        this.__m3tdHideTimelineWidget();
      }
      this.size=[Math.max(this.size?.[0]||0,860),this.size?.[1]||0];
      const root=document.createElement("div");
      const directorWidget=this.addDOMWidget("minimax_h3_timeline","div",root,{serialize:false,hideOnZoom:false});
      requestAnimationFrame(()=>root.parentElement?.classList.add("m3td-widget-host"));
      directorWidget.computeSize=width=>[Math.max(100,(this.size?.[0]||width||860)-20),directorWidget.__m3tdHeight||DIRECTOR_HEIGHT];
      const brand=tr(nodeData.name==="MiniMaxH3TimelinePlanner"?"brandPlanner":"brandDirector");
      this.__m3td=new TimelineDirectorUI(this,root,timelineWidget,brand);
      this.__m3td.directorWidget=directorWidget;
      // The Vue DOM widget can mount one or more frames after onNodeCreated.
      // Retry after mount; subsequent resize/configure hooks keep it hidden.
      for(const delay of [0,50,250,1000])setTimeout(()=>this.__m3tdHideTimelineWidget?.(),delay);
      requestAnimationFrame(()=>{
        this.__m3td?.scheduleNodeHeightSync();
        const computed=this.computeSize?.()||[860,820];
        this.setSize?.([Math.max(860,this.size?.[0]||0,computed[0]||0),computed[1]||820]);
        this.setDirtyCanvas?.(true,true);
      });
      return result;
    };
    const originalResize=nodeType.prototype.onResize;
    nodeType.prototype.onResize=function(){const result=originalResize?.apply(this,arguments);this.__m3tdHideTimelineWidget?.();this.__m3td?.scheduleNodeHeightSync();return result;};
    const originalConfigure=nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure=function(){const result=originalConfigure?.apply(this,arguments);setTimeout(()=>{this.__m3tdHideTimelineWidget?.();this.__m3td?.reload();this.__m3td?.scheduleNodeHeightSync();},0);return result;};
    const originalRemoved=nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved=function(){this.__m3td?.destroy();return originalRemoved?.apply(this,arguments);};
  }
});
