"""Web API for Lumen cases: run a case, read it, record a human sign-off."""
import asyncio
import logging
import secrets
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.common.eventlog import record
from app.orchestrator import run_case
from app.signoff import SignoffError, apply_signoff

log = logging.getLogger("lumen.api")
CONFLICTS = ("closed", "already_signed")


class NewCase(BaseModel):
    notes: str = Field(min_length=20, max_length=4000)


class Signoff(BaseModel):
    role: str = Field(max_length=60)
    name: str = Field(max_length=80)
    decision: str = Field(max_length=20)
    reason: str = Field(default="", max_length=500)


def new_case_id():
    return datetime.now().strftime("A-%m%d-%H%M%S-") + secrets.token_hex(2)


def create_app(agents_factory=None, store=None, runner=run_case):
    web = FastAPI(title="Lumen case API")
    state = {"store": store}

    def get_store():
        if state["store"] is None:
            from app.common.casestore import FirestoreStore

            state["store"] = FirestoreStore()
        return state["store"]

    def get_agents():
        if agents_factory is not None:
            return agents_factory()
        from agents.remote_agents import default_agents

        return default_agents()

    @web.get("/api/health")
    async def health():
        return {"ok": True}

    @web.post("/api/cases")
    async def create_case(body: NewCase):
        case_id = new_case_id()
        try:
            doc = await runner(case_id, body.notes, get_agents(), get_store())
        except Exception:
            log.exception("case run failed")
            return JSONResponse({"error": "run_failed", "case_id": case_id}, status_code=502)
        return JSONResponse(jsonable_encoder(doc))

    @web.get("/api/cases/{case_id}")
    async def read_case(case_id: str):
        doc = await asyncio.to_thread(get_store().get, case_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no such case")
        return JSONResponse(jsonable_encoder(doc))

    @web.post("/api/cases/{case_id}/signoff")
    async def sign(case_id: str, body: Signoff):
        store = get_store()
        doc = await asyncio.to_thread(store.get, case_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no such case")
        try:
            changes = apply_signoff(doc, body.role, body.name, body.decision, body.reason)
        except SignoffError as exc:
            status = 409 if exc.code in CONFLICTS else 422
            return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=status)
        inputs = {"role": body.role, "name": body.name, "decision": body.decision, "reason": body.reason}
        try:
            with record(case_id, "human_signoff", inputs) as run:
                run.finish({"status": changes["status"], "entry": changes["signoffs"][-1]})
            await asyncio.to_thread(store.update, case_id, changes)
        except Exception:
            log.exception("sign-off failed")
            return JSONResponse({"error": "signoff_failed"}, status_code=502)
        doc.update(changes)
        return JSONResponse(jsonable_encoder(doc))

    return web


web = create_app()
