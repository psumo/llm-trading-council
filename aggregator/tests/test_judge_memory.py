"""Judge MEMORY section: build_prompt includes a MEMORY block only when memory
data is supplied (no closed trades -> prompt unchanged)."""
# mypy: ignore-errors
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from judge import build_memory_section, build_prompt  # noqa: E402
from sources.base import Vote  # noqa: E402


def _votes() -> dict:
    return {
        "llm_trader": Vote(source="llm_trader", direction="long", confidence=0.8),
        "llm_tradebot": Vote(source="llm_tradebot", direction="long", confidence=0.7),
        "orderflow": Vote(source="orderflow", direction="short", confidence=0.6),
    }


def test_memory_section_empty_when_no_data() -> None:
    assert build_memory_section(None) == ""
    assert build_memory_section({}) == ""
    assert build_memory_section(
        {"recent_trades": [], "scorecards": [], "lessons": []}
    ) == ""


def test_memory_section_rendered_with_fixture_data() -> None:
    memory = {
        "recent_trades": [
            {
                "direction": "LONG",
                "conviction": 70,
                "outcome": "win",
                "r_multiple": 2.0,
                "regime": "trend",
                "context_line": "session=us agree=2",
            }
        ],
        "scorecards": [
            {
                "source": "llm_trader",
                "hit_rate": 58.0,
                "resolved": 24,
                "regime": "trend",
                "regime_hit_rate": 61.0,
            }
        ],
        "lessons": ["when regime=chop, avoid longs"],
    }
    block = build_memory_section(memory)
    assert "MEMORY" in block
    assert "actual measured performance" in block
    assert "llm_trader" in block
    assert "58.0%" in block
    assert "when regime=chop, avoid longs" in block


def test_build_prompt_includes_memory_when_supplied() -> None:
    memory = {
        "recent_trades": [],
        "scorecards": [],
        "lessons": ["rule one"],
    }
    with_mem = build_prompt(_votes(), "BTCUSDT", 50000.0, memory)
    without_mem = build_prompt(_votes(), "BTCUSDT", 50000.0, None)
    assert "MEMORY" in with_mem
    assert "rule one" in with_mem
    assert "MEMORY" not in without_mem
