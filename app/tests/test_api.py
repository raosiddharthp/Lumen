from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app import api
from app.common.casestore import MemoryStore

NOTES = "44-year-old accountant, breast cancer stage 1, treated six years ago, no recurrence."
APPROVE = {"role": "senior_underwriter", "name": "A. Visser", "decision": "approve"}


def make_doc(case_id, signers=("senior_underwriter",)):
    return {
        "case_id": case_id,
        "status": "awaiting_signoff",
        "referral": {"tier": len(signers), "signers": list(signers)},
        "draft": [],
    }


async def fake_runner(case_id, notes, agents, store):
    doc = make_doc(case_id)
    doc["notes"] = notes
    store.save(doc)
    return doc


async def broken_runner(case_id, notes, agents, store):
    raise RuntimeError("agents down")


@contextmanager
def broken_record(*args, **kwargs):
    raise RuntimeError("log unavailable")
    yield


@pytest.fixture
def events(monkeypatch):
    calls = []

    @contextmanager
    def fake_record(case_id, agent, inputs, sink=None):
        class Run:
            def finish(self, outputs, **kwargs):
                calls.append((case_id, agent, outputs))

        yield Run()

    monkeypatch.setattr(api, "record", fake_record)
    return calls


@pytest.fixture
def setup(events):
    store = MemoryStore()
    app = api.create_app(agents_factory=lambda: None, store=store, runner=fake_runner)
    return TestClient(app), store


def test_health(setup):
    client, _ = setup
    assert client.get("/api/health").json() == {"ok": True}


def test_a_case_can_be_run_and_read_back(setup):
    client, store = setup
    created = client.post("/api/cases", json={"notes": NOTES})
    assert created.status_code == 200
    case_id = created.json()["case_id"]
    assert case_id.startswith("A-")
    assert store.get(case_id) is not None
    assert client.get("/api/cases/" + case_id).json()["notes"] == NOTES


def test_notes_that_are_too_short_are_refused(setup):
    client, _ = setup
    assert client.post("/api/cases", json={"notes": "hi"}).status_code == 422


def test_unknown_cases_are_404(setup):
    client, _ = setup
    assert client.get("/api/cases/nope").status_code == 404
    assert client.post("/api/cases/nope/signoff", json=APPROVE).status_code == 404


def test_an_approval_closes_a_tier_1_case_and_is_logged(setup, events):
    client, store = setup
    store.save(make_doc("C-1"))
    res = client.post("/api/cases/C-1/signoff", json=APPROVE)
    assert res.status_code == 200
    assert res.json()["status"] == "signed_off"
    assert store.get("C-1")["status"] == "signed_off"
    assert [(case, agent) for case, agent, _ in events] == [("C-1", "human_signoff")]


def test_a_second_signature_on_a_closed_case_is_a_conflict(setup):
    client, store = setup
    store.save(make_doc("C-1"))
    assert client.post("/api/cases/C-1/signoff", json=APPROVE).status_code == 200
    again = client.post("/api/cases/C-1/signoff", json=APPROVE)
    assert again.status_code == 409
    assert again.json()["error"] == "closed"


def test_a_role_that_is_not_required_is_refused(setup):
    client, store = setup
    store.save(make_doc("C-1"))
    body = dict(APPROVE, role="cosigner_cmo_or_cuo")
    res = client.post("/api/cases/C-1/signoff", json=body)
    assert res.status_code == 422
    assert res.json()["error"] == "role_not_required"


def test_a_failed_run_is_reported_not_hidden():
    app = api.create_app(agents_factory=lambda: None, store=MemoryStore(), runner=broken_runner)
    res = TestClient(app).post("/api/cases", json={"notes": NOTES})
    assert res.status_code == 502
    assert res.json()["error"] == "run_failed"


def test_a_failed_log_write_blocks_the_signoff(setup, monkeypatch):
    client, store = setup
    store.save(make_doc("C-1"))
    monkeypatch.setattr(api, "record", broken_record)
    res = client.post("/api/cases/C-1/signoff", json=APPROVE)
    assert res.status_code == 502
    assert store.get("C-1")["status"] == "awaiting_signoff"


def test_the_memory_store_applies_updates():
    store = MemoryStore()
    store.save({"case_id": "C-1", "status": "a"})
    store.update("C-1", {"status": "b"})
    assert store.get("C-1")["status"] == "b"


async def fake_warm():
    return {"research": 200, "gate": 200, "drafting": 200}


def test_warming_is_limited_to_once_a_minute():
    now = [0.0]
    app = api.create_app(
        agents_factory=lambda: None, store=MemoryStore(), runner=fake_runner,
        warm=fake_warm, clock=lambda: now[0],
    )
    client = TestClient(app)
    first = client.post("/api/warm").json()
    assert first == {"cached": False, "agents": {"research": 200, "gate": 200, "drafting": 200}}
    assert client.post("/api/warm").json()["cached"] is True
    now[0] = api.WARM_INTERVAL + 1
    assert client.post("/api/warm").json()["cached"] is False


def test_the_page_is_served_from_the_root(setup):
    client, _ = setup
    res = client.get("/")
    assert res.status_code == 200
    assert "Lumen" in res.text


def test_case_responses_carry_the_passages_they_cite(setup):
    client, store = setup
    doc = make_doc("C-9")
    doc["notes"] = "Some notes about the applicant."
    doc["draft"] = [{"id": "s1", "text": "x", "cites": ["CASE", "RG-ONC-002"]}]
    store.save(doc)
    body = client.get("/api/cases/C-9").json()
    assert body["passages"]["CASE"]["text"] == "Some notes about the applicant."
    assert body["passages"]["RG-ONC-002"]["title"] == "Breast cancer, stage I"
    assert "passages" not in store.get("C-9")
