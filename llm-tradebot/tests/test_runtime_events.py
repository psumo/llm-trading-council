import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.runtime_events import emit_runtime_event


class _DummyState:
    def __init__(self):
        self.events = []

    def add_agent_event(self, event):
        self.events.append(event)


def test_emit_runtime_event_increments_sequence_per_run():
    state = _DummyState()

    e1 = emit_runtime_event(
        shared_state=state,
        run_id="run-a",
        stream="lifecycle",
        agent="quant_analyst",
        phase="start",
        cycle_id="cycle-1",
    )
    e2 = emit_runtime_event(
        shared_state=state,
        run_id="run-a",
        stream="lifecycle",
        agent="quant_analyst",
        phase="end",
        cycle_id="cycle-1",
    )

    assert e1["seq"] == 1
    assert e2["seq"] == 2
    assert len(state.events) == 2


def test_emit_runtime_event_resets_sequence_for_new_run():
    state = _DummyState()

    e1 = emit_runtime_event(
        shared_state=state,
        run_id="run-b",
        stream="lifecycle",
        agent="decision_router",
        phase="start",
        cycle_id="cycle-2",
    )
    time.sleep(0.001)
    e2 = emit_runtime_event(
        shared_state=state,
        run_id="run-c",
        stream="lifecycle",
        agent="decision_router",
        phase="start",
        cycle_id="cycle-2",
    )

    assert e1["seq"] == 1
    assert e2["seq"] == 1
    assert e1["run_id"] == "run-b"
    assert e2["run_id"] == "run-c"
