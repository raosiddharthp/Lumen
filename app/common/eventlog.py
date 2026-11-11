import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from .config import PROJECT_ID

COLLECTION = "event_log"
SCHEMA_VERSION = 1
MAX_TEXT = 2000


class MemorySink:
    def __init__(self):
        self.events = []

    def write(self, event):
        self.events.append(event)


class FirestoreSink:
    def __init__(self):
        from google.cloud import firestore

        self._db = firestore.Client(project=PROJECT_ID)

    def write(self, event):
        self._db.collection(COLLECTION).document(event["event_id"]).create(event)


_sink = None


def set_sink(sink):
    global _sink
    _sink = sink


def get_sink():
    global _sink
    if _sink is None:
        if os.environ.get("LUMEN_LOG_SINK") == "memory":
            _sink = MemorySink()
        else:
            _sink = FirestoreSink()
    return _sink


def _clip(value):
    if is_dataclass(value) and not isinstance(value, type):
        return _clip(asdict(value))
    if isinstance(value, str):
        if len(value) <= MAX_TEXT:
            return value
        return value[:MAX_TEXT] + "...[truncated]"
    if isinstance(value, dict):
        return {str(k): _clip(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clip(v) for v in value]
    return value


def _digest(value):
    blob = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Run:
    def __init__(self):
        self.event_id = uuid.uuid4().hex
        self.outputs = {}
        self.confidence = None
        self.status = "ok"
        self.model = None

    def finish(self, outputs, confidence=None, status="ok", model=None):
        self.outputs = outputs
        self.confidence = confidence
        self.status = status
        self.model = model


@contextmanager
def record(case_id, agent, inputs, sink=None):
    run = Run()
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    error = None
    try:
        yield run
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
        run.status = "error"
        raise
    finally:
        clipped_in = _clip(inputs)
        clipped_out = _clip(run.outputs)
        event = {
            "schema_version": SCHEMA_VERSION,
            "event_id": run.event_id,
            "case_id": case_id,
            "agent": agent,
            "model": run.model,
            "status": run.status,
            "error": error,
            "confidence": run.confidence,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "started_at": started,
            "inputs": clipped_in,
            "outputs": clipped_out,
            "inputs_sha256": _digest(clipped_in),
            "outputs_sha256": _digest(clipped_out),
        }
        (sink or get_sink()).write(event)


if __name__ == "__main__":
    with record("SMOKE-001", "smoke", {"note": "log check"}) as run:
        run.finish({"ok": True})
    doc = get_sink()._db.collection(COLLECTION).document(run.event_id).get()
    event = doc.to_dict()
    print("read back:", event["event_id"], event["agent"], event["status"],
          f'{event["latency_ms"]}ms', event["inputs_sha256"][:12])
