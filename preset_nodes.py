"""Local, portable material presets for the MiniMax H3 timeline planner."""

from __future__ import annotations

import copy
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

import folder_paths
from comfy_api.latest import io
from server import PromptServer

from .minimax_h3_finite_segments import FiniteSegmentPlan
from .minimax_h3_timeline_director import FPS, TimelinePlan, _require_timeline_plan, _safe_input_path


PresetData = io.Custom("MINIMAX_H3_TIMELINE_PRESET")
PRESET_FORMAT = "minimax-h3-timeline-preset"
PRESET_SCHEMA_VERSION = 1
PRESET_OUTPUT_SUBDIR = "MiniMaxH3_Presets"
PRESET_INPUT_SUBDIR = "minimax_h3_timeline_director/presets"
EMPTY_PRESET = "(no presets found)"
SAVE_MODES = ["configuration", "complete"]


def _preset_root() -> Path:
    root = Path(folder_paths.get_output_directory()).resolve() / PRESET_OUTPUT_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_component(value: str, fallback: str = "preset") -> str:
    name = re.sub(r"[^\w.()\-\u4e00-\u9fff]+", "_", str(value or "").strip(), flags=re.UNICODE)
    name = name.strip(" ._")
    return (name or fallback)[:120]


def _preset_names() -> list[str]:
    root = _preset_root()
    return sorted(
        path.name for path in root.iterdir()
        if path.is_dir() and (path / "preset.json").is_file() and not path.name.startswith(".")
    )


def _preset_directory(name: str) -> Path:
    root = _preset_root()
    candidate = (root / str(name or "")).resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Preset path is outside the local preset directory") from exc
    if len(relative.parts) != 1 or candidate.name.startswith("."):
        raise ValueError("Preset name must identify one local preset folder")
    if not (candidate / "preset.json").is_file():
        raise FileNotFoundError(f"Preset not found: {name}")
    return candidate


def _read_preset(name: str) -> tuple[Path, dict[str, Any]]:
    directory = _preset_directory(name)
    try:
        data = json.loads((directory / "preset.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("preset.json is not valid JSON") from exc
    if not isinstance(data, dict) or data.get("format") != PRESET_FORMAT:
        raise ValueError("The folder does not contain a MiniMax H3 timeline preset")
    if int(data.get("schema_version") or 0) != PRESET_SCHEMA_VERSION:
        raise ValueError(f"Unsupported preset schema version: {data.get('schema_version')}")
    if data.get("preset_type") not in SAVE_MODES:
        raise ValueError("Preset type must be configuration or complete")
    timeline = data.get("timeline")
    canvas = data.get("canvas")
    if not isinstance(timeline, dict) or not isinstance(canvas, dict):
        raise ValueError("Preset is missing timeline or canvas configuration")
    return directory, data


def _source_plan(material_plan: Any = None, segment_plan: Any = None) -> dict[str, Any]:
    value = segment_plan if segment_plan is not None else material_plan
    if value is None:
        raise ValueError("Connect Material Plan or Segment Plan before exporting a preset")
    if isinstance(value, dict) and value.get("type") == "minimax_h3_finite_segment_plan":
        value = value.get("source_plan")
    return copy.deepcopy(_require_timeline_plan(value))


def _portable_timeline(plan: dict[str, Any]) -> dict[str, Any]:
    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if (
                    "lora" in normalized
                    or normalized in {"secondpassmodel", "modelname", "checkpoint", "checkpointname"}
                    or normalized in {"pluginversion", "comfyversion", "comfyuiversion"}
                ):
                    continue
                cleaned[key] = scrub(item)
            return cleaned
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return copy.deepcopy(value)

    timeline = scrub(plan["timeline"])
    for clip in timeline.get("videoClips", []):
        if isinstance(clip, dict):
            clip.pop("proxy", None)
            clip.pop("peaks", None)
    return timeline


def _unused_target(directory: Path) -> Path:
    if not directory.exists():
        return directory
    for index in range(2, 10000):
        candidate = directory.with_name(f"{directory.name}_{index}")
        if not candidate.exists():
            return candidate
    raise ValueError("Too many presets use the same name")


def _copy_media(timeline: dict[str, Any], staging: Path) -> None:
    media_root = staging / "media"
    copied: dict[str, str] = {}
    used_names: set[str] = set()
    collections = (
        (timeline.get("videoClips", []), "videos"),
        (timeline.get("images", []), "images"),
        (timeline.get("audios", []), "audios"),
    )
    for assets, kind in collections:
        for asset in assets:
            if not isinstance(asset, dict) or not asset.get("file"):
                continue
            source = _safe_input_path(str(asset["file"]))
            source_key = str(source).casefold()
            relative = copied.get(source_key)
            if relative is None:
                base = _safe_component(source.name, "media")
                stem, suffix = Path(base).stem, Path(base).suffix
                filename = base
                counter = 2
                while f"{kind}/{filename}".casefold() in used_names:
                    filename = f"{stem}_{counter}{suffix}"
                    counter += 1
                used_names.add(f"{kind}/{filename}".casefold())
                destination = media_root / kind / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                relative = destination.relative_to(staging).as_posix()
                copied[source_key] = relative
            asset["file"] = relative


def _materialize_media(directory: Path, data: dict[str, Any]) -> dict[str, Any]:
    timeline = copy.deepcopy(data["timeline"])
    if data["preset_type"] != "complete":
        return timeline
    destination_root = (
        Path(folder_paths.get_input_directory()).resolve()
        / PRESET_INPUT_SUBDIR
        / _safe_component(directory.name)
    )
    collections = (
        timeline.get("videoClips", []), timeline.get("images", []), timeline.get("audios", [])
    )
    for assets in collections:
        for asset in assets:
            if not isinstance(asset, dict) or not asset.get("file"):
                continue
            source = (directory / str(asset["file"])).resolve()
            try:
                relative = source.relative_to(directory)
            except ValueError as exc:
                raise ValueError("Preset media path is outside the preset folder") from exc
            if not source.is_file() or not relative.parts or relative.parts[0] != "media":
                raise FileNotFoundError(f"Preset media is missing: {asset['file']}")
            destination = (destination_root / Path(*relative.parts[1:])).resolve()
            try:
                destination.relative_to(destination_root)
            except ValueError as exc:
                raise ValueError("Preset media destination is outside the input directory") from exc
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            asset["file"] = destination.relative_to(Path(folder_paths.get_input_directory()).resolve()).as_posix()
    return timeline


def _preset_payload(name: str) -> dict[str, Any]:
    directory, data = _read_preset(name)
    canvas = data["canvas"]
    timeline = _materialize_media(directory, data)
    timeline.pop("secondPassModel", None)
    return {
        "type": "MINIMAX_H3_TIMELINE_PRESET",
        "name": directory.name,
        "preset_type": data["preset_type"],
        "width": max(32, int(canvas.get("width") or 1344)),
        "height": max(32, int(canvas.get("height") or 768)),
        "generation_seconds": max(5.0 / FPS, float(canvas.get("generation_seconds") or 5.0)),
        "timeline": timeline,
    }


class MiniMaxH3PresetLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        names = _preset_names() or [EMPTY_PRESET]
        return io.Schema(
            node_id="MiniMaxH3PresetLoader",
            display_name="MiniMax H3 Local Preset Loader",
            description="Find a local timeline preset and feed it into the Material Planner.",
            category="MiniMax H3/Presets",
            inputs=[io.Combo.Input("preset_name", options=names, default=names[0])],
            outputs=[
                PresetData.Output(display_name="Preset Data"),
                io.String.Output(display_name="Preset Name"),
                io.String.Output(display_name="Preset Status"),
            ],
        )

    @classmethod
    def execute(cls, preset_name):
        if preset_name == EMPTY_PRESET:
            raise ValueError("No local MiniMax H3 presets were found")
        preset = _preset_payload(str(preset_name))
        return io.NodeOutput(preset, preset["name"], f"Loaded preset: {preset['name']}")


class MiniMaxH3PresetExporter(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3PresetExporter",
            display_name="MiniMax H3 Preset Export",
            description="Save timeline configuration alone or with all referenced media in a portable local folder.",
            category="MiniMax H3/Presets",
            is_output_node=True,
            inputs=[
                io.String.Input("preset_name", default="MiniMaxH3_Preset"),
                io.Combo.Input("save_mode", options=SAVE_MODES, default="configuration"),
                TimelinePlan.Input("material_plan", optional=True, display_name="Material Plan"),
                FiniteSegmentPlan.Input("segment_plan", optional=True, display_name="Segment Plan"),
            ],
            outputs=[
                io.String.Output(display_name="Saved Folder"),
                io.String.Output(display_name="Save Status"),
            ],
        )

    @classmethod
    def execute(cls, preset_name, save_mode, material_plan=None, segment_plan=None):
        if material_plan is not None and segment_plan is not None:
            raise ValueError("Connect either Material Plan or Segment Plan, not both")
        if save_mode not in SAVE_MODES:
            raise ValueError("Save mode must be configuration or complete")
        plan = _source_plan(material_plan, segment_plan)
        timeline = _portable_timeline(plan)
        name = _safe_component(preset_name, "MiniMaxH3_Preset")
        target = _unused_target(_preset_root() / name)
        staging = _preset_root() / f".{target.name}.tmp-{uuid.uuid4().hex}"
        staging.mkdir(parents=True)
        try:
            if save_mode == "complete":
                _copy_media(timeline, staging)
            payload = {
                "format": PRESET_FORMAT,
                "schema_version": PRESET_SCHEMA_VERSION,
                "name": target.name,
                "preset_type": save_mode,
                "canvas": {
                    "width": int(plan["width"]),
                    "height": int(plan["height"]),
                    "generation_seconds": float(plan["generation_seconds"]),
                    "fps": int(FPS),
                },
                "sampling": {
                    "second_pass": bool(timeline.get("secondPass")),
                    "high_resolution_steps": max(1, int(timeline.get("secondPassHighSteps") or 4)),
                },
                "timeline": timeline,
            }
            (staging / "preset.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            staging.rename(target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        status = f"Saved {save_mode} preset: {target.name}"
        return io.NodeOutput(str(target), status)


@PromptServer.instance.routes.get("/minimax_h3_timeline/presets/list")
async def list_presets(_request: web.Request) -> web.Response:
    return web.json_response({"presets": _preset_names()})


@PromptServer.instance.routes.post("/minimax_h3_timeline/presets/load")
async def load_preset(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return web.json_response(_preset_payload(str(payload.get("preset_name") or "")))
    except FileNotFoundError as exc:
        return web.json_response({"error": str(exc)}, status=404)
    except (ValueError, json.JSONDecodeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
