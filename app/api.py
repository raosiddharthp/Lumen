"""Web API for Lumen cases: run a case, read it, record a human sign-off."""
import asyncio
import logging
import pathlib
import secrets
import time
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.common.eventlog import record
from app.common.hydrate import hydrate
from app.guard import FirestoreCounters, Guard
from app.orchestrator import run_case
from app.recorded import load as default_recorded
from app.signoff import SignoffError, apply_signoff

log = logging.getLogger("lumen.api")
CONFLICTS = ("closed", "already_signed")
WARM_INTERVAL = 60
WEB_DIR = pathlib.Path(__file__).parent / "web"


class NewCase(BaseModel):
    notes: str = Field(min_length=20, max_length=4000)


class Signoff(BaseModel):
    role: str = Field(max_length=60)
    name: str = Field(max_length=80)
    decision: str = Field(max_length=20)
    reason: str = Field(default="", max_length=500)


def new_case_id():
    return datetime.now().strftime("A-%m%d-%H%M%S-") + secrets.token_hex(8)


def reply(doc):
    """A case as JSON, with the text of every passage it cites attached."""
    return JSONResponse(jsonable_encoder(hydrate(doc)))


def caller_address(request):
    """The caller's address: the last X-Forwarded-For entry, which Cloud Run adds itself."""
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if parts:
        return parts[-1]
    return request.client.host if request.client else "unknown"


async def warm_agents():
    """Call each agent card so scaled-to-zero services wake up. Returns HTTP codes."""
    import httpx

    from agents.cloud_auth import CALL_TIMEOUT, authed_client
    from agents.remote_agents import AGENT_CARD_WELL_KNOWN_PATH, agent_urls

    async def ping(name, url):
        client = authed_client(url) or httpx.AsyncClient(timeout=CALL_TIMEOUT)
        try:
            res = await asyncio.wait_for(client.get(url + AGENT_CARD_WELL_KNOWN_PATH), 90)
            return name, res.status_code
        except Exception:
            return name, 0
        finally:
            await client.aclose()

    pairs = await asyncio.gather(*(ping(n, u) for n, u in agent_urls().items()))
    return dict(pairs)


def create_app(agents_factory=None, store=None, runner=run_case, warm=None, clock=time.monotonic, guard=None, recorded=None):
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

    @web.get("/api/limits")
    async def limits(request: Request):
        if guard is None:
            return {"live": True, "left": None, "remaining": {}}
        decision = await asyncio.to_thread(guard.status, caller_address(request))
        return {
            "live": decision.ok,
            "reason": decision.reason,
            "left": decision.left,
            "remaining": decision.remaining,
            "message": decision.message,
        }

    @web.post("/api/cases")
    async def create_case(body: NewCase, request: Request):
        if guard is not None:
            decision = await asyncio.to_thread(guard.reserve, caller_address(request))
            if not decision.ok:
                return JSONResponse(
                    {
                        "error": "limit",
                        "reason": decision.reason,
                        "message": decision.message,
                        "remaining": decision.remaining,
                    },
                    status_code=429,
                )
        case_id = new_case_id()
        try:
            doc = await runner(case_id, body.notes, get_agents(), get_store())
        except Exception:
            log.exception("case run failed")
            return JSONResponse({"error": "run_failed", "case_id": case_id}, status_code=502)
        return reply(doc)

    @web.get("/api/cases/{case_id}")
    async def read_case(case_id: str):
        doc = await asyncio.to_thread(get_store().get, case_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="no such case")
        return reply(doc)

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
        return reply(doc)

    @web.get("/api/recorded")
    async def recorded_run():
        snapshot = await asyncio.to_thread(recorded or default_recorded)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="no recorded run")
        return JSONResponse(snapshot)

    last = {"at": None, "agents": None}

    @web.post("/api/warm")
    async def warm_up():
        now = clock()
        if last["at"] is not None and now - last["at"] < WARM_INTERVAL:
            return {"cached": True, "agents": last["agents"]}
        last["at"] = now
        last["agents"] = await (warm or warm_agents)()
        return {"cached": False, "agents": last["agents"]}

    if WEB_DIR.is_dir():
        web.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
    return web


web = create_app(guard=Guard(FirestoreCounters()))
