"""MiniMax H3 Timeline Director for ComfyUI."""

from .minimax_h3_timeline_director import MiniMaxH3TimelineDirector

NODE_CLASS_MAPPINGS = {
    "MiniMaxH3TimelineDirector": MiniMaxH3TimelineDirector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3TimelineDirector": "MiniMax H3 时间线导演台",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
