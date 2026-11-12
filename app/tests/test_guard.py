from datetime import datetime, timezone

from app.guard import Guard, MemoryCounters

DEFAULT = {"visitor_day": 2, "global_day": 6, "global_month": 60}


def make(limits=None, salt="s"):
    now = {"t": datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)}
    guard = Guard(MemoryCounters(), limits or dict(DEFAULT), salt=salt, clock=lambda: now["t"])
    return guard, now


def test_first_run_is_allowed_and_counted():
    guard, _ = make()
    d = guard.reserve("1.2.3.4")
    assert d.ok and d.reason is None
    assert d.remaining == {"visitor_day": 1, "global_day": 5, "global_month": 59}
    assert d.left == 1


def test_visitor_limit_blocks_only_that_visitor():
    guard, _ = make()
    assert guard.reserve("1.1.1.1").ok
    assert guard.reserve("1.1.1.1").ok
    d = guard.reserve("1.1.1.1")
    assert not d.ok and d.reason == "visitor_day"
    assert d.message
    assert guard.reserve("2.2.2.2").ok


def test_global_day_limit():
    guard, _ = make({"visitor_day": 99, "global_day": 3, "global_month": 60})
    for i in range(3):
        assert guard.reserve(f"10.0.0.{i}").ok
    d = guard.reserve("10.0.0.9")
    assert not d.ok and d.reason == "global_day"


def test_global_month_limit():
    guard, _ = make({"visitor_day": 99, "global_day": 99, "global_month": 2})
    assert guard.reserve("a").ok
    assert guard.reserve("b").ok
    d = guard.reserve("c")
    assert not d.ok and d.reason == "global_month"


def test_refusal_does_not_use_up_a_run():
    guard, _ = make({"visitor_day": 1, "global_day": 6, "global_month": 60})
    assert guard.reserve("a").ok
    assert not guard.reserve("a").ok
    assert not guard.reserve("a").ok
    assert guard.status("b").remaining["global_day"] == 5


def test_new_day_resets_daily_counts_but_not_the_month():
    guard, now = make({"visitor_day": 1, "global_day": 1, "global_month": 2})
    assert guard.reserve("a").ok
    assert not guard.reserve("a").ok
    now["t"] = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
    assert guard.reserve("a").ok
    now["t"] = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)
    d = guard.reserve("a")
    assert not d.ok and d.reason == "global_month"


def test_visitor_id_is_stable_hidden_and_salted():
    a, _ = make(salt="one")
    b, _ = make(salt="two")
    assert a.visitor_id("1.2.3.4") == a.visitor_id("1.2.3.4")
    assert "1.2.3.4" not in a.visitor_id("1.2.3.4")
    assert a.visitor_id("1.2.3.4") != b.visitor_id("1.2.3.4")
    assert a.visitor_id("1.2.3.4") != a.visitor_id("1.2.3.5")


def test_status_does_not_use_up_a_run():
    guard, _ = make()
    before = guard.status("a")
    after = guard.status("a")
    assert before.remaining == after.remaining
    assert before.left == 2


def test_guard_fails_closed_when_the_counters_break():
    class Broken:
        def reserve(self, checks):
            raise RuntimeError("firestore down")

        def counts(self, keys):
            raise RuntimeError("firestore down")

    guard = Guard(Broken(), dict(DEFAULT), salt="s")
    assert guard.reserve("a").reason == "guard_error"
    d = guard.status("a")
    assert not d.ok and d.reason == "guard_error"
    assert d.message
