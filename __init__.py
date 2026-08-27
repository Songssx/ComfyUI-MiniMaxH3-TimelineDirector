"""MiniMax H3 Timeline Director for ComfyUI."""

from .minimax_h3_timeline_director import (
    MiniMaxH3TimelineDirector,
    MiniMaxH3TimelineEncoder,
    MiniMaxH3OmniPromptBridge,
    MiniMaxH3TimelinePlanner,
)

NODE_CLASS_MAPPINGS = {
    "MiniMaxH3TimelineDirector": MiniMaxH3TimelineDirector,
    "MiniMaxH3TimelinePlanner": MiniMaxH3TimelinePlanner,
    "MiniMaxH3TimelineEncoder": MiniMaxH3TimelineEncoder,
    "MiniMaxH3OmniPromptBridge": MiniMaxH3OmniPromptBridge,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3TimelineDirector": "MiniMax H3 时间线导演台",
    "MiniMaxH3TimelinePlanner": "MiniMax H3 素材规划台",
    "MiniMaxH3TimelineEncoder": "MiniMax H3 规划编码器",
    "MiniMaxH3OmniPromptBridge": "MiniMax H3 Omni 素材包提示词桥",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
