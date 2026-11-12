"""A recorded run: a real case saved as a file, shown when live runs are not available."""
import json
import pathlib
from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder

from .common.hydrate import hydrate

PATH = pathlib.Path(__file__).parent / "data" / "recorded" / "sample.json"


def export_case(store, case_id, now=None):
    doc = store.get(case_id)
    if doc is None:
        raise KeyError(case_id)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    out = hydrate(doc)
    out["recorded"] = {"at": stamp, "source_case": case_id}
    return jsonable_encoder(out)


def save(snapshot, path=PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def load(path=PATH):
    if not path.is_file():
        return None
    return json.loads(path.read_text())


if __name__ == "__main__":
    import sys

    from .common.casestore import FirestoreStore

    save(export_case(FirestoreStore(), sys.argv[1]))
    print("saved", PATH)
