import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const NODE_NAME = "MiniMaxH3TimelineDirector";
const STYLE_ID = "m3td-style";
const CHUNK_SIZE = 4 * 1024 * 1024;

function installStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .m3td { --bg:#11141b; --panel:#191e28; --line:#30384a; --text:#e9eef8; --muted:#919bad;
      --cyan:#43d9d1; --blue:#477ff0; --amber:#f3af4e; --red:#ef6a77; box-sizing:border-box;
      width:100%; max-width:100%; height:100%; min-height:520px; color:var(--text); background:var(--bg); border:1px solid #2b3241;
      border-radius:9px; overflow:hidden; font:12px/1.35 Inter,Segoe UI,Arial,sans-serif; user-select:none; }
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
    .m3td-settings { display:flex; align-items:center; gap:12px; padding:7px 10px; border-bottom:1px solid var(--line); background:#151a22; }
    .m3td-field { display:flex; align-items:center; gap:5px; color:var(--muted); }
    .m3td-field input { width:72px; height:25px; padding:2px 5px; color:var(--text); background:#0d1118;
      border:1px solid #333d50; border-radius:4px; outline:none; user-select:text; }
    .m3td-field input:focus { border-color:var(--cyan); }
    .m3td-help { margin-left:auto; color:#9da9bc; }
    .m3td-timeline-shell { display:grid; grid-template-columns:108px minmax(0,1fr); border-bottom:1px solid var(--line); }
    .m3td-labels { background:#151a22; border-right:1px solid var(--line); padding-top:26px; }
    .m3td-track-label { display:flex; height:94px; align-items:center; padding:0 10px; border-top:1px solid #272e3b; color:#aab5c7; }
    .m3td-track-label.audio { height:50px; color:#c0a36f; }
    .m3td-audio-toggle { margin-left:auto; height:22px; padding:0 6px; border:1px solid #6c5638; border-radius:4px;
      color:#f3cf92; background:#382d20; cursor:pointer; font-size:10px; }
    .m3td-audio-toggle.off { color:#c3cad5; background:#282d36; border-color:#4c5565; }
    .m3td-viewport { position:relative; overflow:auto; background:#0e1219; scrollbar-color:#49556a #171c25; }
    .m3td-stage { position:relative; min-width:100%; height:170px; }
    .m3td-ruler { position:relative; height:26px; border-bottom:1px solid #2c3443; background:#131821; }
    .m3td-tick { position:absolute; bottom:0; width:1px; height:8px; background:#556074; color:#8490a4; }
    .m3td-tick.major { height:13px; background:#78849a; }
    .m3td-tick span { position:absolute; left:4px; top:-11px; white-space:nowrap; font-size:10px; }
    .m3td-track { position:relative; height:94px; border-bottom:1px solid #262d3a;
      background-image:linear-gradient(90deg,rgba(255,255,255,.027) 1px,transparent 1px); }
    .m3td-track.audio { height:50px; background-color:#111720; }
    .m3td-track.audio.muted .m3td-audio-clip { opacity:.28; filter:grayscale(1); }
    .m3td-clip { position:absolute; top:8px; height:78px; min-width:10px; overflow:hidden; border:1px solid #5688ec;
      border-radius:5px; background:#223c6e; cursor:grab; box-shadow:0 3px 10px #0007; }
    .m3td-clip.selected { border:2px solid #b9ddff; box-shadow:0 0 0 2px #328bff99,0 5px 14px #0009; }
    .m3td-clip video { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; opacity:.62; pointer-events:none; }
    .m3td-clip-shade { position:absolute; inset:0; background:linear-gradient(180deg,#0002,#061329cc); }
    .m3td-clip-name { position:absolute; left:9px; right:8px; top:7px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
      font-weight:600; text-shadow:0 1px 2px #000; }
    .m3td-clip-meta { position:absolute; left:9px; bottom:6px; color:#c8d9f7; text-shadow:0 1px 2px #000; }
    .m3td-clip-ref { position:absolute; right:6px; top:6px; z-index:3; padding:1px 4px; border-radius:3px;
      color:#dffcff; background:#102432dc; font-size:10px; font-weight:700; }
    .m3td-clip-ref.guide { top:24px; color:#78fff5; border:1px solid #43d9d177; }
    .m3td-handle { position:absolute; top:0; bottom:0; width:7px; z-index:4; cursor:ew-resize; }
    .m3td-handle.left { left:0; } .m3td-handle.right { right:0; }
    .m3td-audio-clip { position:absolute; top:5px; height:40px; overflow:hidden; border:1px solid #a77636; border-radius:4px;
      background:#44351f; opacity:.92; }
    .m3td-wave { width:100%; height:100%; display:block; }
    .m3td-selection { position:absolute; top:26px; height:144px; z-index:8; border:2px solid var(--cyan);
      background:rgba(35,211,199,.10); box-shadow:inset 0 0 25px #43d9d116; pointer-events:auto; cursor:move; }
    .m3td-selection::before { content:"GEN"; position:absolute; top:2px; left:5px; font-size:9px; font-weight:800; color:#72fff5; }
    .m3td-selection .m3td-sel-handle { position:absolute; top:0; bottom:0; width:9px; background:#43d9d155; cursor:ew-resize; }
    .m3td-selection .left { left:-5px; } .m3td-selection .right { right:-5px; }
    .m3td-playhead { position:absolute; top:0; bottom:0; width:9px; margin-left:-4px; z-index:11; cursor:ew-resize; }
    .m3td-playhead::before { content:""; position:absolute; left:0; top:0; border-left:4px solid transparent;
      border-right:4px solid transparent; border-top:7px solid #ff737d; }
    .m3td-playhead::after { content:""; position:absolute; left:4px; top:0; bottom:0; width:1px; background:#ff737d; }
    .m3td-snap-guide { position:absolute; top:0; bottom:0; width:1px; z-index:12; pointer-events:none;
      background:#ffe178; box-shadow:0 0 5px #ffe178; }
    .m3td-inspector { display:flex; gap:10px; align-items:center; min-height:38px; padding:6px 10px; background:#171c25;
      border-bottom:1px solid var(--line); color:var(--muted); }
    .m3td-inspector strong { color:#dfe8f7; max-width:190px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .m3td-inspector .m3td-field input { width:66px; }
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
      background:#242c39; cursor:pointer; }
    .m3td-asset img { width:100%; height:100%; object-fit:cover; }
    .m3td-asset.audio { width:120px; color:#e0c28e; padding:7px 20px 5px 7px; }
    .m3td-asset-tag { position:absolute; left:3px; top:2px; z-index:2; padding:1px 3px; border-radius:3px;
      color:#fff4c9; background:#111c; font-size:10px; font-weight:700; }
    .m3td-asset-name { position:absolute; left:3px; right:3px; bottom:2px; padding:1px 2px; overflow:hidden; text-overflow:ellipsis;
      white-space:nowrap; background:#000a; color:#fff; font-size:10px; }
    .m3td-asset-x { position:absolute; right:2px; top:2px; width:17px; height:17px; border:0; border-radius:50%; color:#fff;
      background:#9c3345cc; cursor:pointer; }
    .m3td-foot { display:flex; align-items:center; gap:9px; min-height:31px; padding:5px 9px; color:#8f9bad; background:#141922; }
    .m3td-tags { color:#a9d8d4; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .m3td-progress { width:90px; height:4px; overflow:hidden; border-radius:2px; background:#303746; }
    .m3td-progress > i { display:block; height:100%; width:0; background:var(--cyan); }
  `;
  document.head.appendChild(style);
}

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
const num = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function emptyState() {
  return { version: 2, fps: 24, selection: { start: 0, duration: 5 }, videoAudioEnabled: true, videoClips: [], images: [], audios: [] };
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
    proxy: c.proxy || "",
    peaks: Array.isArray(c.peaks) ? c.peaks : [],
  })) : [];
  base.images = Array.isArray(raw.images) ? raw.images.filter(x => x?.file).slice(0, 9).map(a => ({ id:a.id || uid(), ...a })) : [];
  base.audios = Array.isArray(raw.audios) ? raw.audios.filter(x => x?.file).slice(0, 3).map(a => ({ id:a.id || uid(), ...a })) : [];
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
  constructor(node, root, widget) {
    this.node = node;
    this.root = root;
    this.widget = widget;
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
    this.previewClipId = null;
    this.build();
    this.bindGenerationWidget();
    this.syncGenerationWidget();
    this.render();
    this.attachGlobalPointerHandlers();
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
    for (const clip of ordered) {
      const overlapStart = Math.max(start, clip.start), overlapEnd = Math.min(end, clipEnd(clip));
      const overlap = overlapEnd - overlapStart;
      if (overlap <= 0) continue;
      const guideFrames = Math.max(1, Math.round(overlap * 24));
      guidePieces.push({clipId:clip.id, frames:guideFrames, hasAudio:this.state.videoAudioEnabled && !!clip.hasAudio});
      const outside = [];
      if (clip.start < start) outside.push(Math.min(clipEnd(clip), start) - clip.start);
      if (clipEnd(clip) > end) outside.push(clipEnd(clip) - Math.max(clip.start, end));
      for (let remaining of outside) while (remaining >= 5/24 && videoPieces.length < 3) {
        const seconds = Math.min(15, remaining);
        const hasAudio = this.state.videoAudioEnabled && !!clip.hasAudio;
        videoPieces.push({clipId: clip.id, seconds, hasAudio});
        if (hasAudio) pairedAudioCount++;
        remaining -= seconds;
      }
    }
    let gapGuideCount = 0;
    if (!guidePieces.length) {
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
        <span class="m3td-brand">MiniMax H3 时间线导演台</span>
        <button class="m3td-btn" data-action="video">＋ 视频</button>
        <button class="m3td-btn" data-action="image">＋ 图片</button>
        <button class="m3td-btn" data-action="audio">＋ 音频</button>
        <button class="m3td-btn" data-action="split">✂ 在播放头分段</button>
        <button class="m3td-btn danger" data-action="delete">删除片段</button>
        <span class="m3td-spacer"></span><span class="m3td-status">就绪</span>
        <span class="m3td-progress"><i></i></span>
      </div>
      <div class="m3td-settings">
        <label class="m3td-field">选区起点 <input data-field="selectionStart" type="number" min="0" step="0.04"></label>
        <label class="m3td-field">参考时长 <input data-field="selectionDuration" type="number" min="0.21" step="0.04"></label>
        <label class="m3td-field">缩放 <input data-field="zoom" type="range" min="24" max="180" step="4"></label>
        <button class="m3td-btn" data-action="fit">适应全部</button>
        <button class="m3td-btn" data-action="fitGap">匹配最近空隙</button>
        <span class="m3td-help">拖动片段/播放头 · 边缘自动吸附 · 选区时长=生成时长</span>
      </div>
      <div class="m3td-timeline-shell">
        <div class="m3td-labels"><div class="m3td-track-label">参考视频</div><div class="m3td-track-label audio"><span>视频原声</span><button class="m3td-audio-toggle" data-action="videoAudioToggle" type="button">关闭</button></div></div>
        <div class="m3td-viewport"><div class="m3td-stage"></div></div>
      </div>
      <div class="m3td-inspector"><span>未选中片段</span></div>
      <div class="m3td-preview">
        <div class="m3td-preview-screen"><video class="m3td-preview-video" muted playsinline preload="metadata"></video><div class="m3td-preview-empty">拖动红色播放头到视频片段上，即可查看当前位置画面</div></div>
        <div class="m3td-preview-side">
          <div class="m3td-preview-title">低清视频监看 · 最高 480×270 / 12fps</div>
          <div class="m3td-preview-time">00:00.00</div>
          <div class="m3td-preview-name">当前没有可预览的视频</div>
          <button class="m3td-btn" data-action="previewPlay">▶ 播放预览</button>
          <div class="m3td-preview-note">仅预览使用低清无声代理；最终生成读取原始视频，视频原声是否参与参考由轨道开关控制。</div>
        </div>
      </div>
      <div class="m3td-assets">
        <section class="m3td-bin"><div class="m3td-bin-title"><span>独立参考图片（0/9）</span><span>&lt;Picture i&gt;</span></div><div class="m3td-bin-list" data-bin="images"></div></section>
        <section class="m3td-bin"><div class="m3td-bin-title"><span>独立参考音频（0/3）</span><span>&lt;Audio j&gt;</span></div><div class="m3td-bin-list" data-bin="audios"></div></section>
      </div>
      <div class="m3td-foot"><strong>提示词编号：</strong><span class="m3td-tags"></span></div>
      <input hidden data-upload="video" type="file" accept="video/*">
      <input hidden data-upload="image" type="file" accept="image/*">
      <input hidden data-upload="audio" type="file" accept="audio/*">
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
    this.videoAudioToggle.onclick = event => {
      event.stopPropagation();
      this.state.videoAudioEnabled = !this.state.videoAudioEnabled;
      this.sync(); this.render();
      this.setStatus(this.state.videoAudioEnabled ? "视频原声参考已开启" : "视频原声参考已关闭");
    };
    this.previewPlay.onclick = () => this.togglePreviewPlayback();
    this.previewVideo.onplay = () => { this.previewPlay.textContent = "❚❚ 暂停预览"; };
    this.previewVideo.onpause = () => { this.previewPlay.textContent = "▶ 播放预览"; };
    this.previewVideo.ontimeupdate = () => this.followPreviewPlayback();
    this.previewVideo.onended = () => { this.previewPlay.textContent = "▶ 播放预览"; };
    for (const input of this.root.querySelectorAll("[data-upload]")) {
      input.onchange = async () => { if (input.files?.[0]) await this.addFile(input.dataset.upload, input.files[0]); input.value = ""; };
    }
    const startInput = this.root.querySelector('[data-field="selectionStart"]');
    const durInput = this.root.querySelector('[data-field="selectionDuration"]');
    const zoomInput = this.root.querySelector('[data-field="zoom"]');
    this.root.addEventListener("input", event => {
      if (event.target === startInput) {
        this.state.selection.start = Math.max(0, num(startInput.value));
        this.playhead = this.state.selection.start;
        this.sync();
      } else if (event.target === durInput) {
        this.state.selection.duration = Math.max(5/24, num(durInput.value, 5));
        this.sync();
      }
    });
    startInput.onchange = durInput.onchange = () => this.render();
    zoomInput.oninput = () => { this.zoom = num(zoomInput.value, 64); this.renderTimeline(); };
    this.viewport.addEventListener("pointerdown", e => {
      if (e.target.closest(".m3td-clip,.m3td-selection,.m3td-playhead")) return;
      this.beginPlayheadDrag(e);
    });
    this.viewport.addEventListener("dblclick", e => {
      if (e.target.closest(".m3td-clip")) return;
      this.fitSelectionToGapAt(this.timeFromClientX(e.clientX));
    });
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
    if (this.videoAudioToggle) {
      this.videoAudioToggle.textContent = this.state.videoAudioEnabled ? "关闭" : "开启";
      this.videoAudioToggle.classList.toggle("off", !this.state.videoAudioEnabled);
      this.videoAudioToggle.title = this.state.videoAudioEnabled ? "点击后视频仍参与参考，但不传入视频原声" : "点击后恢复视频原声参考";
      this.videoAudioToggle.setAttribute("aria-pressed", String(this.state.videoAudioEnabled));
    }
    this.renderTimeline();
    this.renderInspector();
    this.renderAssets();
    this.renderTags();
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
    html += `<div class="m3td-selection" data-role="selection" style="left:${sel.start*this.zoom}px;width:${Math.max(8,sel.duration*this.zoom)}px"><i class="m3td-sel-handle left" data-edge="left"></i><i class="m3td-sel-handle right" data-edge="right"></i></div>`;
    if (this.snapGuide != null) html += `<div class="m3td-snap-guide" style="left:${this.snapGuide*this.zoom}px"></div>`;
    html += `<div class="m3td-playhead" data-role="playhead" title="拖动播放头" style="left:${this.playhead*this.zoom}px"></div>`;
    this.stage.innerHTML = html;
    for (const el of this.stage.querySelectorAll(".m3td-clip")) {
      const clip = this.state.videoClips.find(c => c.id === el.dataset.id);
      el.onpointerdown = e => this.beginClipDrag(e, clip, e.target.dataset.edge || "move");
      const video = el.querySelector("video");
      if (video && clip) video.addEventListener("loadedmetadata", () => { try { video.currentTime = Math.min(clip.trimStart + .05, Math.max(0, video.duration-.05)); } catch (_) {} }, {once:true});
    }
    const selection = this.stage.querySelector(".m3td-selection");
    selection.onpointerdown = e => this.beginSelectionDrag(e, e.target.dataset.edge || "move");
    this.stage.querySelector(".m3td-playhead").onpointerdown = e => this.beginPlayheadDrag(e);
    this.drawWaveforms();
    this.schedulePreviewUpdate();
  }

  clipHTML(clip, plan) {
    const left = clip.start * this.zoom, width = Math.max(10, clip.duration * this.zoom);
    const videoIndex = plan.videoPieces.findIndex(piece => piece.clipId === clip.id);
    const guide = plan.guidePieces.find(piece => piece.clipId === clip.id);
    const refTag = `${videoIndex >= 0 ? `<span class="m3td-clip-ref">&lt;Video ${videoIndex+1}&gt;</span>` : ""}${guide ? `<span class="m3td-clip-ref guide">GUIDE ${guide.frames}帧</span>` : ""}`;
    return `<div class="m3td-clip ${clip.id === this.selectedId ? "selected" : ""}" data-id="${esc(clip.id)}" style="left:${left}px;width:${width}px">
      <video muted preload="metadata" src="${esc(viewURL(clip.file))}"></video><div class="m3td-clip-shade"></div>
      <i class="m3td-handle left" data-edge="left"></i><i class="m3td-handle right" data-edge="right"></i>
      <span class="m3td-clip-name">${esc(clip.name)}</span>${refTag}<span class="m3td-clip-meta">${clip.duration.toFixed(2)}s · 源 ${clip.trimStart.toFixed(2)}s</span></div>`;
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
      this.previewEmpty.textContent = "正在生成低清代理视频，首次预览请稍候…";
      this.setStatus(`正在生成低清预览：${clip.name}`);
      const params = new URLSearchParams({filename: clip.file});
      const response = await api.fetchApi(`/minimax_h3_timeline/preview_proxy?${params.toString()}`);
      const payload = await response.json();
      if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
      clip.proxy = payload.proxy;
      this.sync();
      this.setStatus(`低清预览已就绪：${clip.name}`);
      return clip.proxy;
    })().catch(error => {
      console.error("[MiniMaxH3TimelineDirector] preview proxy", error);
      this.previewEmpty.textContent = `预览生成失败：${error.message}`;
      this.setStatus(`预览失败：${error.message}`);
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
      this.previewEmpty.textContent = "红色播放头当前位置没有视频片段";
      this.previewName.textContent = "当前没有可预览的视频";
      this.previewTime.textContent = this.formatPreviewTime(this.playhead);
      this.previewClipId = null;
      return;
    }
    const sourceTime = this.previewSourceTime(clip);
    this.previewTime.textContent = `${this.formatPreviewTime(this.playhead)}  ·  源 ${this.formatPreviewTime(sourceTime)}`;
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
    if (!clip) { this.setStatus("请先把红色播放头移动到视频片段上"); return; }
    try {
      await this.ensurePreviewProxy(clip);
      await this.updatePreview(true);
      if (this.previewVideo.readyState < 1) {
        await new Promise(resolve => this.previewVideo.addEventListener("loadedmetadata", resolve, {once:true}));
      }
      this.previewVideo.currentTime = clamp(this.previewSourceTime(clip), 0, Math.max(0, this.previewVideo.duration - .01));
      await this.previewVideo.play();
    } catch (error) {
      this.setStatus(`无法播放预览：${error.message}`);
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
    this.previewTime.textContent = `${this.formatPreviewTime(this.playhead)}  ·  源 ${this.formatPreviewTime(this.previewVideo.currentTime)}`;
    this.renderTimeline();
  }

  beginClipDrag(event, clip, mode) {
    if (!clip) return;
    event.preventDefault(); event.stopPropagation();
    this.selectedId = clip.id;
    const rect = this.stage.getBoundingClientRect();
    const canvasScale = rect.width / Math.max(1, this.stage.offsetWidth);
    this.drag = { kind:"clip", mode, x:event.clientX, scale:canvasScale, start:clip.start, duration:clip.duration, trimStart:clip.trimStart, clip };
    this.render();
  }

  beginSelectionDrag(event, mode) {
    event.preventDefault(); event.stopPropagation();
    const rect = this.stage.getBoundingClientRect();
    const canvasScale = rect.width / Math.max(1, this.stage.offsetWidth);
    this.drag = { kind:"selection", mode, x:event.clientX, scale:canvasScale, start:this.state.selection.start, duration:this.state.selection.duration };
  }

  beginPlayheadDrag(event) {
    event.preventDefault(); event.stopPropagation();
    this.previewVideo.pause();
    const snapped = this.snapValue(this.timeFromClientX(event.clientX), this.snapPoints(null, true));
    this.playhead = snapped.value;
    this.snapGuide = snapped.snapAt;
    this.drag = {kind:"playhead"};
    this.renderTimeline();
  }

  attachGlobalPointerHandlers() {
    this.pointerMove = e => {
      if (!this.drag) return;
      if (this.drag.kind === "playhead") {
        const snapped = this.snapValue(this.timeFromClientX(e.clientX), this.snapPoints(null, true));
        this.playhead = snapped.value; this.snapGuide = snapped.snapAt; this.renderTimeline(); return;
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
      this.sync(); this.render();
    };
    this.pointerUp = () => { if (this.drag) { this.drag = null; this.snapGuide = null; this.sync(); this.render(); } };
    window.addEventListener("pointermove", this.pointerMove);
    window.addEventListener("pointerup", this.pointerUp);
  }

  renderInspector() {
    const clip = this.state.videoClips.find(c => c.id === this.selectedId);
    if (!clip) { this.inspector.innerHTML = '<span>未选中片段：单击视频片段后可精确输入位置与裁剪值</span>'; return; }
    this.inspector.innerHTML = `<strong title="${esc(clip.name)}">${esc(clip.name)}</strong>
      <label class="m3td-field">起点 <input data-edit="start" type="number" min="0" step="0.04" value="${clip.start.toFixed(2)}"></label>
      <label class="m3td-field">源入点 <input data-edit="trimStart" type="number" min="0" step="0.04" value="${clip.trimStart.toFixed(2)}"></label>
      <label class="m3td-field">片段长度 <input data-edit="duration" type="number" min="0.21" step="0.04" value="${clip.duration.toFixed(2)}"></label>
      <span>${clip.hasAudio ? (this.state.videoAudioEnabled ? "✓ 原声参考开启" : "⊘ 原声参考关闭") : "— 无原声"}</span>`;
    for (const input of this.inspector.querySelectorAll("input[data-edit]")) input.onchange = () => {
      const key=input.dataset.edit, value=Math.max(0,num(input.value));
      if (key === "duration") clip.duration=clamp(value,5/24,Math.max(5/24,clip.sourceDuration-clip.trimStart));
      else if (key === "trimStart") { clip.trimStart=clamp(value,0,Math.max(0,clip.sourceDuration-5/24)); clip.duration=Math.min(clip.duration,clip.sourceDuration-clip.trimStart); }
      else clip.start=value;
      this.sync(); this.render();
    };
  }

  renderAssets() {
    const imageBin = this.root.querySelector('[data-bin="images"]');
    const audioBin = this.root.querySelector('[data-bin="audios"]');
    this.root.querySelectorAll(".m3td-bin-title span:first-child")[0].textContent = `独立参考图片（${this.state.images.length}/9）`;
    this.root.querySelectorAll(".m3td-bin-title span:first-child")[1].textContent = `独立参考音频（${this.state.audios.length}/3）`;
    imageBin.innerHTML = this.state.images.map((a,i) => `<div class="m3td-asset"><img src="${esc(viewURL(a.file))}"><span class="m3td-asset-tag">&lt;Picture ${i+1}&gt;</span><span class="m3td-asset-name">${esc(a.name)}</span><button class="m3td-asset-x" data-remove-image="${esc(a.id)}">×</button></div>`).join("");
    audioBin.innerHTML = this.state.audios.map((a,i) => `<div class="m3td-asset audio"><span class="m3td-asset-tag">&lt;Audio ${i+1}&gt;</span><span class="m3td-asset-name">${esc(a.name)}</span><button class="m3td-asset-x" data-remove-audio="${esc(a.id)}">×</button></div>`).join("");
    for (const b of imageBin.querySelectorAll("[data-remove-image]")) b.onclick=e=>{e.stopPropagation();this.state.images=this.state.images.filter(a=>a.id!==b.dataset.removeImage);this.sync();this.render();};
    for (const b of audioBin.querySelectorAll("[data-remove-audio]")) b.onclick=e=>{e.stopPropagation();this.state.audios=this.state.audios.filter(a=>a.id!==b.dataset.removeAudio);this.sync();this.render();};
  }

  renderTags() {
    const plan=this.referencePlan();
    const independentPictures=this.state.images.length;
    const videoText=plan.videoPieces.length ? `区外参考视频 <Video 1..${plan.videoPieces.length}>` : "无普通视频参考";
    const audioTotal=plan.pairedAudioCount+this.state.audios.length;
    const pictureText=independentPictures ? `独立图片 <Picture 1..${independentPictures}>` : "无独立图片";
    const guideFrames=plan.guidePieces.reduce((sum,item)=>sum+item.frames,0);
    const guideText=plan.guidePieces.length ? `原生固定 Guide ${plan.guidePieces.length}段/${guideFrames}帧` : (plan.gapGuideCount ? `空隙首尾 Guide ${plan.gapGuideCount}帧` : "无固定 Guide");
    const standaloneAudio=this.state.audios.length ? `独立音频 <Audio 1..${this.state.audios.length}>` : "无独立音频";
    const pairedAudio=!this.state.videoAudioEnabled ? "视频原声：参考已关闭" : (plan.pairedAudioCount ? `视频原声 <Audio ${this.state.audios.length+1}..${audioTotal}>` : "无视频原声标签");
    this.root.querySelector(".m3td-tags").textContent = `${pictureText} · ${guideText} · ${videoText} · ${standaloneAudio} · ${pairedAudio}`;
  }

  splitSelected() {
    const index=this.state.videoClips.findIndex(c=>c.id===this.selectedId); if(index<0)return;
    const clip=this.state.videoClips[index], cut=this.playhead-clip.start;
    if(cut<=5/24 || cut>=clip.duration-5/24){this.setStatus("播放头需在所选片段内部");return;}
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
    if(!gaps.length){this.setStatus("当前视频片段之间没有可匹配的空隙");return;}
    const gap=gaps.reduce((best,current)=>{
      const distance=time<current.start?current.start-time:time>current.start+current.duration?time-current.start-current.duration:0;
      const bestDistance=time<best.start?best.start-time:time>best.start+best.duration?time-best.start-best.duration:0;
      return distance<bestDistance?current:best;
    });
    this.state.selection.start=gap.start;this.state.selection.duration=gap.duration;this.playhead=gap.start;
    this.sync();this.render();this.setStatus(`生成选区已匹配空隙：${gap.duration.toFixed(2)} 秒`);
  }

  fitSelectionToNearestGap() {
    const anchor=this.state.selection.start+this.state.selection.duration/2;
    this.fitSelectionToGapAt(anchor);
  }

  setStatus(message, progress=null) { this.status.textContent=message; if(progress!=null)this.progress.style.width=`${clamp(progress,0,1)*100}%`; }

  async addFile(kind,file) {
    if(this.uploading)return;
    if(kind==="image"&&this.state.images.length>=9){this.setStatus("图片最多 9 张");return;}
    if(kind==="audio"&&this.state.audios.length>=3){this.setStatus("独立音频最多 3 段");return;}
    this.uploading=true;
    try{
      const serverName=`${Date.now()}_${Math.random().toString(36).slice(2,7)}_${file.name.replace(/[^\w.()\-\u4e00-\u9fff]+/gu,"_")}`;
      const total=Math.max(1,Math.ceil(file.size/CHUNK_SIZE));let info=null;
      for(let index=0;index<total;index++){
        const data=new FormData();data.append("file",file.slice(index*CHUNK_SIZE,Math.min(file.size,(index+1)*CHUNK_SIZE)),file.name);
        data.append("filename",serverName);data.append("chunk_index",String(index));data.append("total_chunks",String(total));
        this.setStatus(`上传 ${file.name} ${index+1}/${total}`,index/total);
        const response=await api.fetchApi("/minimax_h3_timeline/upload_chunk",{method:"POST",body:data});
        const payload=await response.json();if(!response.ok||payload.error)throw new Error(payload.error||`HTTP ${response.status}`);info=payload;
      }
      if(kind==="video"){
        if(!info.hasVideo)throw new Error("上传的文件不包含视频轨");
        const start=this.state.videoClips.reduce((m,c)=>Math.max(m,c.start+c.duration),0);
        const duration=Math.max(5/24,num(info.duration,5));
        const clip={id:uid(),file:info.filename,name:file.name,start,duration,trimStart:0,sourceDuration:duration,hasAudio:!!info.hasAudio,peaks:info.peaks||[],proxy:""};
        this.state.videoClips.push(clip);this.selectedId=clip.id;
      }else if(kind==="image")this.state.images.push({id:uid(),file:info.filename,name:file.name,width:info.width||0,height:info.height||0});
      else { if(!info.hasAudio)throw new Error("上传的文件不包含音频轨"); this.state.audios.push({id:uid(),file:info.filename,name:file.name,duration:info.duration||0,trimStart:0}); }
      this.sync();this.render();this.setStatus(`已添加 ${file.name}`,1);
    }catch(error){console.error("[MiniMaxH3TimelineDirector]",error);this.setStatus(`失败：${error.message}`,0);}
    finally{this.uploading=false;setTimeout(()=>{this.progress.style.width="0";},800);}
  }

  reload() { this.previewVideo?.pause();this.state=normalizeState(this.readWidget());this.selectedId=null;this.playhead=this.state.selection.start;this.previewClipId=null;this.bindGenerationWidget();this.syncGenerationWidget();this.render(); }
  destroy() { cancelAnimationFrame(this.previewRAF);this.previewVideo?.pause();window.removeEventListener("pointermove",this.pointerMove);window.removeEventListener("pointerup",this.pointerUp); }
}

app.registerExtension({
  name: "MiniMaxH3.TimelineDirector",
  async beforeRegisterNodeDef(nodeType,nodeData) {
    if(nodeData.name!==NODE_NAME)return;
    installStyles();
    const originalCreated=nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated=function(){
      const result=originalCreated?.apply(this,arguments);
      const timelineWidget=this.widgets?.find(w=>w.name==="timeline_data");
      if(timelineWidget){
        timelineWidget.type="hidden"; timelineWidget.computeSize=()=>[0,-4];
        const timelineElement=timelineWidget.element || timelineWidget.inputEl;
        if(timelineElement){timelineElement.style.display="none";timelineElement.parentElement && (timelineElement.parentElement.style.display="none");}
      }
      this.size=[Math.max(this.size?.[0]||0,860),Math.max(this.size?.[1]||0,1040)];
      const root=document.createElement("div");
      const directorWidget=this.addDOMWidget("minimax_h3_timeline","div",root,{serialize:false,hideOnZoom:false});
      directorWidget.computeSize=width=>[Math.max(100,(this.size?.[0]||width||860)-20),750];
      this.__m3td=new TimelineDirectorUI(this,root,timelineWidget);
      requestAnimationFrame(()=>{
        const computed=this.computeSize?.()||[860,820];
        this.setSize?.([Math.max(860,this.size?.[0]||0,computed[0]||0),Math.max(1040,this.size?.[1]||0,computed[1]||0)]);
        this.setDirtyCanvas?.(true,true);
      });
      return result;
    };
    const originalConfigure=nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure=function(){const result=originalConfigure?.apply(this,arguments);setTimeout(()=>this.__m3td?.reload(),0);return result;};
    const originalRemoved=nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved=function(){this.__m3td?.destroy();return originalRemoved?.apply(this,arguments);};
  }
});
