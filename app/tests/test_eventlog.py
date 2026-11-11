import pytest

from app.common.eventlog import MAX_TEXT, MemorySink, _digest, record
from app.common.rating import Factors, rate


def test_ok_run_is_recorded():
    sink = MemorySink()
    with record("A-1", "research", {"q": "stage I"}, sink=sink) as run:
        run.finish({"hits": 3}, confidence=0.8, model="m1")
    e = sink.events[0]
    assert e["case_id"] == "A-1" and e["agent"] == "research"
    assert e["status"] == "ok" and e["confidence"] == 0.8 and e["model"] == "m1"
    assert e["outputs"] == {"hits": 3}


def test_error_is_logged_and_reraised():
    sink = MemorySink()
    with pytest.raises(ValueError):
        with record("A-2", "drafting", {}, sink=sink):
            raise ValueError("boom")
    e = sink.events[0]
    assert e["status"] == "error" and "ValueError: boom" in e["error"]


def test_digests_are_stable_and_order_independent():
    assert _digest({"a": 1, "b": 2}) == _digest({"b": 2, "a": 1})
    assert _digest({"a": 1}) != _digest({"a": 2})


def test_long_text_is_truncated():
    sink = MemorySink()
    with record("A-3", "research", {"text": "x" * 5000}, sink=sink) as run:
        run.finish({})
    stored = sink.events[0]["inputs"]["text"]
    assert len(stored) < 5000 and stored.endswith("[truncated]")
    assert stored.startswith("x" * MAX_TEXT)


def test_event_ids_are_unique():
    sink = MemorySink()
    for _ in range(5):
        with record("A-4", "gate", {}, sink=sink) as run:
            run.finish({})
    assert len({e["event_id"] for e in sink.events}) == 5


def test_confidence_is_optional():
    sink = MemorySink()
    with record("A-5", "rating", {}, sink=sink) as run:
        run.finish({"ok": True})
    assert sink.events[0]["confidence"] is None


def test_dataclasses_are_stored_as_plain_data():
    sink = MemorySink()
    f = Factors(condition="none")
    with record("A-6", "rating", f, sink=sink) as run:
        run.finish(rate(f))
    e = sink.events[0]
    assert e["inputs"]["condition"] == "none"
    assert e["outputs"]["methodology_version"] == "v4.2"
    assert isinstance(e["outputs"]["rule_ids"], list)
