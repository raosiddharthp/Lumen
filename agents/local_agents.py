import asyncio
import sys
from datetime import datetime

from agents.drafting.local import run_draft
from agents.gate.local import run_gate
from agents.research.local import SAMPLE, run_research
from app.common.casestore import FirestoreStore
from app.orchestrator import run_case


class LocalAgents:
    async def research(self, case_id, notes):
        result, _retrieved, tokens = await run_research(case_id, notes)
        return result, tokens

    async def gate(self, case_id, claims, stage, lookup):
        return await run_gate(case_id, claims, stage, lookup)

    async def draft(self, case_id, notes, rating, evidence_ids):
        return await run_draft(case_id, notes, rating, evidence_ids)


def summarise(doc):
    rating, referral = doc["rating"], doc["referral"]
    print("\ncase:", doc["case_id"])
    print("factors:", doc["factors"])
    print("rating:", rating["status"], rating["loading_pct"], rating["rule_ids"])
    print("evidence kept:", doc["evidence"]["verified"],
          "| dropped:", doc["evidence"]["dropped"])
    print("grounding:", doc["grounding"], "| stages:", doc["stages"])
    print("referral: tier", referral["tier"], referral["signers"], referral["reasons"])
    print("draft sentences:", len(doc["draft"]) if doc["draft"] else 0)
    print("tokens in/out:", doc["tokens"]["in"], doc["tokens"]["out"])


if __name__ == "__main__":
    notes = sys.argv[1] if len(sys.argv) > 1 else SAMPLE
    case_id = datetime.now().strftime("L-%m%d-%H%M%S")
    store = FirestoreStore()
    doc = asyncio.run(run_case(case_id, notes, LocalAgents(), store))
    summarise(doc)
    stored = store.get(case_id)
    print("read back from Firestore:", stored["status"], "tier", stored["referral"]["tier"])
