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
from .minimax_h3_finite_segments import (
    MiniMaxH3LongReferenceSegmentPlan,
    MiniMaxH3FiniteLatentContinuation,
    MiniMaxH3FiniteSegmentExpansion,
    MiniMaxH3FiniteAudioTrimTail,
    MiniMaxH3FiniteOutputTrim,
    MiniMaxH3FiniteSegmentFinalize,
    MiniMaxH3FiniteSegmentSampler,
)

NODE_CLASS_MAPPINGS = {
    "MiniMaxH3TimelineDirector": MiniMaxH3TimelineDirector,
    "MiniMaxH3TimelinePlanner": MiniMaxH3TimelinePlanner,
    "MiniMaxH3TimelineEncoder": MiniMaxH3TimelineEncoder,
    "MiniMaxH3OmniPromptBridge": MiniMaxH3OmniPromptBridge,
    "MiniMaxH3AddLatentGuide": MiniMaxH3AddLatentGuide,
    "MiniMaxH3VisualDifferenceMetrics": MiniMaxH3VisualDifferenceMetrics,
    "MiniMaxH3FiniteSegmentExpansion": MiniMaxH3FiniteSegmentExpansion,
    "MiniMaxH3LongReferenceSegmentPlan": MiniMaxH3LongReferenceSegmentPlan,
    "MiniMaxH3FiniteSegmentSampler": MiniMaxH3FiniteSegmentSampler,
    "MiniMaxH3FiniteAudioTrimTail": MiniMaxH3FiniteAudioTrimTail,
    "MiniMaxH3FiniteOutputTrim": MiniMaxH3FiniteOutputTrim,
    "MiniMaxH3FiniteLatentContinuation": MiniMaxH3FiniteLatentContinuation,
    "MiniMaxH3FiniteSegmentFinalize": MiniMaxH3FiniteSegmentFinalize,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3TimelineDirector": "MiniMax H3 Timeline Director",
    "MiniMaxH3TimelinePlanner": "MiniMax H3 Material Planner",
    "MiniMaxH3TimelineEncoder": "MiniMax H3 Plan Encoder",
    "MiniMaxH3OmniPromptBridge": "MiniMax H3 Omni Media Prompt Bridge",
    "MiniMaxH3AddLatentGuide": "MiniMax H3 Direct Latent Guide (Experimental)",
    "MiniMaxH3VisualDifferenceMetrics": "MiniMax H3 Video Difference Metrics (Experimental)",
    "MiniMaxH3FiniteSegmentExpansion": "MiniMax H3 Finite Segment Expansion",
    "MiniMaxH3LongReferenceSegmentPlan": "MiniMax H3 Long Reference Auto Segmentation",
    "MiniMaxH3FiniteSegmentSampler": "MiniMax H3 Finite Segment Sampler",
    "MiniMaxH3FiniteAudioTrimTail": "MiniMax H3 Finite Audio Tail Trim (Internal)",
    "MiniMaxH3FiniteOutputTrim": "MiniMax H3 Finite Output Trim (Internal)",
    "MiniMaxH3FiniteLatentContinuation": "MiniMax H3 Finite Latent Continuation (Internal)",
    "MiniMaxH3FiniteSegmentFinalize": "MiniMax H3 Finite Segment Finalize (Internal)",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
