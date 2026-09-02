"""Static localization smoke checks."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NODES = {
    "MiniMaxH3TimelineDirector", "MiniMaxH3TimelinePlanner",
    "MiniMaxH3TimelineEncoder", "MiniMaxH3OmniPromptBridge",
    "MiniMaxH3AddLatentGuide", "MiniMaxH3VisualDifferenceMetrics",
    "MiniMaxH3FiniteSegmentExpansion", "MiniMaxH3FiniteSegmentSampler",
    "MiniMaxH3FiniteLatentContinuation", "MiniMaxH3FiniteSegmentFinalize",
}


def load(language: str, filename: str) -> dict:
    return json.loads((ROOT / "locales" / language / filename).read_text(encoding="utf-8"))


def main() -> None:
    en_main, zh_main = load("en", "main.json"), load("zh", "main.json")
    en_nodes, zh_nodes = load("en", "nodeDefs.json"), load("zh", "nodeDefs.json")
    en_timeline = en_main["MiniMaxH3TimelineDirector"]["timeline"]
    zh_timeline = zh_main["MiniMaxH3TimelineDirector"]["timeline"]
    assert set(en_timeline) == set(zh_timeline)
    assert set(en_nodes) == EXPECTED_NODES == set(zh_nodes)

    javascript = (ROOT / "js/minimax_h3_timeline_director.js").read_text(encoding="utf-8")
    used_keys = set(re.findall(r'\btr\("([A-Za-z0-9_]+)"', javascript))
    missing = used_keys - set(en_timeline)
    assert not missing, f"Timeline translation keys are missing: {sorted(missing)}"

    for relative in (
        "__init__.py", "minimax_h3_timeline_director.py",
        "minimax_h3_finite_segments.py", "experimental_latent_guide.py",
        "js/minimax_h3_timeline_director.js",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert not re.search(r"[\u3400-\u9fff]", source), f"Hard-coded CJK remains in {relative}"
    print("localization smoke test: PASS")


if __name__ == "__main__":
    main()
