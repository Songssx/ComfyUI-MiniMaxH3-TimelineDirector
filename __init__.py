"""MiniMax H3 Timeline Director for ComfyUI."""

from .minimax_h3_timeline_director import (
    MiniMaxH3TimelineDirector,
    MiniMaxH3TimelineEncoder,
    MiniMaxH3OmniPromptBridge,
    MiniMaxH3TimelinePlanner,
)
from .experimental_latent_guide import (
    MiniMaxH3AddLatentGuide,
    MiniMaxH3VisualDifferenceMetrics,
)
from .minimax_h3_loop import (
    MiniMaxH3LoopLatentGuide,
    MiniMaxH3LoopPromptSelector,
    MiniMaxH3LoopSegmentFinalize,
)

NODE_CLASS_MAPPINGS = {
    "MiniMaxH3TimelineDirector": MiniMaxH3TimelineDirector,
    "MiniMaxH3TimelinePlanner": MiniMaxH3TimelinePlanner,
    "MiniMaxH3TimelineEncoder": MiniMaxH3TimelineEncoder,
    "MiniMaxH3OmniPromptBridge": MiniMaxH3OmniPromptBridge,
    "MiniMaxH3AddLatentGuide": MiniMaxH3AddLatentGuide,
    "MiniMaxH3VisualDifferenceMetrics": MiniMaxH3VisualDifferenceMetrics,
    "MiniMaxH3LoopPromptSelector": MiniMaxH3LoopPromptSelector,
    "MiniMaxH3LoopLatentGuide": MiniMaxH3LoopLatentGuide,
    "MiniMaxH3LoopSegmentFinalize": MiniMaxH3LoopSegmentFinalize,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3TimelineDirector": "MiniMax H3 时间线导演台",
    "MiniMaxH3TimelinePlanner": "MiniMax H3 素材规划台",
    "MiniMaxH3TimelineEncoder": "MiniMax H3 规划编码器",
    "MiniMaxH3OmniPromptBridge": "MiniMax H3 Omni 素材包提示词桥",
    "MiniMaxH3AddLatentGuide": "MiniMax H3 直接 Latent Guide（实验）",
    "MiniMaxH3VisualDifferenceMetrics": "MiniMax H3 视频差异指标（实验）",
    "MiniMaxH3LoopPromptSelector": "MiniMax H3 循环分段提示词",
    "MiniMaxH3LoopLatentGuide": "MiniMax H3 Latent 循环续段",
    "MiniMaxH3LoopSegmentFinalize": "MiniMax H3 循环片段去重",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
