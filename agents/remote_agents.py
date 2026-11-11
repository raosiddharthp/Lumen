import asyncio
import sys
from datetime import datetime

from google.adk.agents.remote_a2a_agent import (
    AGENT_CARD_WELL_KNOWN_PATH,
    RemoteA2aAgent,
)
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.common.draft import (
    DraftError,
    allowed_ids_for,
    build_draft_prompt,
    parse_draft,
)
from app.common.eventlog import record
from app.common.grounding import (
    GroundingError,
    build_gate_prompt,
    decide,
    parse_verdicts,
)
from app.common.research_result import ResearchError, parse_result


class RemoteTransport:
    def __init__(self, base_url: str, name: str):
        self.card = base_url.rstrip("/") + AGENT_CARD_WELL_KNOWN_PATH
        self.name = name

    async def ask(self, user_id: str, text: str) -> str:
        remote = RemoteA2aAgent(
            name=self.name,
            agent_card=self.card,
            description=f"{self.name} reached over A2A",
        )
        runner = InMemoryRunner(agent=remote, app_name=self.name)
        session = await runner.session_service.create_session(
            app_name=self.name, user_id=user_id
        )
        msg = types.Content(role="user", parts=[types.Part(text=text)])
        final = ""
        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=msg
        ):
            if event.is_final_response() and event.content:
                final = event.content.parts[0].text
        return final


class A2AAgents:
    def __init__(self, research, gate, drafting, known_ids=None, lookup=None):
        self._research = research
        self._gate = gate
        self._drafting = drafting
        self._known_ids = known_ids
        self._lookup = lookup

    def _ids(self):
        if self._known_ids is None:
            from app.common import passages

            return passages.known_ids()
        return self._known_ids()

    def _passage(self):
        if self._lookup is None:
            from app.common import passages

            return passages.get_passage
        return self._lookup

    async def research(self, case_id, notes):
        inputs = {"notes": notes, "transport": "a2a"}
        with record(case_id, "research", inputs) as run:
            text = await self._research.ask(case_id, notes)
            try:
                result = parse_result(text, self._ids())
            except ResearchError as exc:
                run.finish({"raw": text, "error": exc.code}, status="error")
                raise
            run.finish({"result": result.model_dump(exclude_none=True)})
        return result, (0, 0)

    async def gate(self, case_id, claims, stage, lookup):
        inputs = {"stage": stage, "claims": claims, "transport": "a2a"}
        with record(case_id, "grounding_gate", inputs) as run:
            prompt = build_gate_prompt(claims, lookup or self._passage())
            text = await self._gate.ask(case_id, prompt)
            try:
                verdicts = parse_verdicts(text, claims)
            except GroundingError as exc:
                run.finish({"raw": text, "error": exc.code, "decision": "hard_stop"},
                           status="error")
                raise
            decision = decide(claims, verdicts)
            run.finish({"decision": decision, "verdicts": verdicts})
        return decision, verdicts, (0, 0)

    async def draft(self, case_id, notes, rating, evidence_ids):
        inputs = {"evidence_ids": evidence_ids, "rating": rating, "transport": "a2a"}
        with record(case_id, "drafting", inputs) as run:
            prompt = build_draft_prompt(notes, rating, evidence_ids, self._passage())
            text = await self._drafting.ask(case_id, prompt)
            try:
                claims = parse_draft(text, allowed_ids_for(evidence_ids))
            except DraftError as exc:
                run.finish({"raw": text, "error": exc.code}, status="error")
                raise
            run.finish({"claims": claims})
        return claims, (0, 0)


def default_agents(host: str = "http://localhost") -> A2AAgents:
    return A2AAgents(
        RemoteTransport(f"{host}:8011", "research_remote"),
        RemoteTransport(f"{host}:8012", "gate_remote"),
        RemoteTransport(f"{host}:8013", "drafting_remote"),
    )


if __name__ == "__main__":
    from agents.local_agents import summarise
    from agents.research.local import SAMPLE
    from app.common.casestore import FirestoreStore
    from app.orchestrator import run_case

    notes = sys.argv[1] if len(sys.argv) > 1 else SAMPLE
    case_id = datetime.now().strftime("A-%m%d-%H%M%S")
    store = FirestoreStore()
    doc = asyncio.run(run_case(case_id, notes, default_agents(), store))
    summarise(doc)
    stored = store.get(case_id)
    print("read back from Firestore:", stored["status"], "tier", stored["referral"]["tier"])
