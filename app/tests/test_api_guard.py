from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api import create_app, new_case_id
from app.common.casestore import MemoryStore
from app.guard import Guard, MemoryCounters

NOTES = "Female, 52. Stage I breast cancer treated six years ago, surveillance clear."
DEFAULT = {"visitor_day": 2, "global_day": 6, "global_month": 60}


async def fake_runner(case_id, notes, agents, store):
    doc = {
        "case_id": case_id,
        "notes": notes,
        "status": "awaiting_signoff",
        "draft": [],
        "evidence": {"verified": [], "dropped": []},
        "rating": None,
        "factors": {},
        "tokens": {"in": 0, "out": 0},
    }
    store.save(doc)
    return doc


def make_client(limits=None, runner=fake_runner):
    guard = Guard(
        MemoryCounters(),
        limits or dict(DEFAULT),
        salt="s",
        clock=lambda: datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
    )
    app = create_app(agents_factory=lambda: None, store=MemoryStore(), runner=runner, guard=guard)
    return TestClient(app)


def post(client, address="1.1.1.1"):
    return client.post("/api/cases", json={"notes": NOTES}, headers={"x-forwarded-for": address})


def test_new_case_ids_are_long_and_unique():
    ids = {new_case_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(len(i) >= 28 for i in ids)


def test_visitor_limit_returns_429_and_other_visitors_still_run():
    client = make_client()
    assert post(client).status_code == 200
    assert post(client).status_code == 200
    res = post(client)
    assert res.status_code == 429
    body = res.json()
    assert body["error"] == "limit" and body["reason"] == "visitor_day"
    assert body["message"]
    assert post(client, "2.2.2.2").status_code == 200


def test_a_refused_run_never_reaches_the_agents():
    calls = []

    async def counting_runner(case_id, notes, agents, store):
        calls.append(case_id)
        return await fake_runner(case_id, notes, agents, store)

    client = make_client({"visitor_day": 1, "global_day": 6, "global_month": 60}, counting_runner)
    assert post(client).status_code == 200
    assert post(client).status_code == 429
    assert len(calls) == 1


def test_limits_endpoint_reports_remaining_without_using_a_run():
    client = make_client()
    headers = {"x-forwarded-for": "1.1.1.1"}
    first = client.get("/api/limits", headers=headers).json()
    again = client.get("/api/limits", headers=headers).json()
    assert first == again
    assert first["live"] is True and first["left"] == 2
    post(client)
    assert client.get("/api/limits", headers=headers).json()["left"] == 1


def test_without_a_guard_runs_are_unlimited():
    app = create_app(agents_factory=lambda: None, store=MemoryStore(), runner=fake_runner)
    client = TestClient(app)
    for _ in range(5):
        assert client.post("/api/cases", json={"notes": NOTES}).status_code == 200
    assert client.get("/api/limits").json()["left"] is None


def test_a_broken_guard_blocks_runs():
    class Broken:
        def reserve(self, checks):
            raise RuntimeError("firestore down")

        def counts(self, keys):
            raise RuntimeError("firestore down")

    called = []

    async def runner(case_id, notes, agents, store):
        called.append(case_id)
        return await fake_runner(case_id, notes, agents, store)

    guard = Guard(Broken(), dict(DEFAULT), salt="s")
    app = create_app(agents_factory=lambda: None, store=MemoryStore(), runner=runner, guard=guard)
    res = TestClient(app).post("/api/cases", json={"notes": NOTES})
    assert res.status_code == 429 and res.json()["reason"] == "guard_error"
    assert called == []
