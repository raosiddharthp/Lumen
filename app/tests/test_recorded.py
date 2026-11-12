from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.common.casestore import MemoryStore
from app.recorded import export_case, load, save

DOC = {
    "case_id": "L-1",
    "notes": "Stage I breast cancer, treated six years ago.",
    "status": "awaiting_signoff",
    "draft": [{"text": "A sentence.", "cites": ["CASE"]}],
    "evidence": {"verified": [], "dropped": []},
    "rating": None,
}
NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)
SNAPSHOT = {"case_id": "L-1", "recorded": {"at": "2026-11-12"}}


def test_export_attaches_passages_and_a_recording_note():
    store = MemoryStore()
    store.save(dict(DOC))
    out = export_case(store, "L-1", now=NOW)
    assert out["passages"]["CASE"]["text"] == DOC["notes"]
    assert out["recorded"] == {"at": "2026-11-12", "source_case": "L-1"}
    assert out["case_id"] == "L-1"


def test_export_of_an_unknown_case_fails():
    with pytest.raises(KeyError):
        export_case(MemoryStore(), "nope", now=NOW)


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "recorded" / "sample.json"
    save(SNAPSHOT, path)
    assert load(path) == SNAPSHOT


def test_load_returns_none_when_nothing_is_recorded(tmp_path):
    assert load(tmp_path / "missing.json") is None


def test_recorded_route_serves_the_snapshot():
    client = TestClient(create_app(store=MemoryStore(), recorded=lambda: SNAPSHOT))
    res = client.get("/api/recorded")
    assert res.status_code == 200
    assert res.json()["recorded"]["at"] == "2026-11-12"


def test_recorded_route_is_404_when_nothing_is_recorded():
    client = TestClient(create_app(store=MemoryStore(), recorded=lambda: None))
    assert client.get("/api/recorded").status_code == 404
