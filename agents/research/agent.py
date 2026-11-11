import datetime as dt

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext

from app.common import config, retrieval
from app.common.llm import configure_vertex
from app.common.rating import OCCUPATION, RULES

configure_vertex()


def _search(corpus: str, query: str, tool_context: ToolContext) -> dict:
    hits = retrieval.search(query, corpus, k=3)
    seen = tool_context.state.get("retrieved", [])
    tool_context.state["retrieved"] = seen + [h["citation_id"] for h in hits]
    return {
        "results": [
            {"citation_id": h["citation_id"], "title": h["title"], "text": h["text"]}
            for h in hits
        ]
    }


def search_guidance(query: str, tool_context: ToolContext) -> dict:
    """Search the underwriting guidance rules. Returns the three closest passages with their citation IDs."""
    return _search("guidance", query, tool_context)


def search_precedent(query: str, tool_context: ToolContext) -> dict:
    """Search past decided cases. Returns the three closest precedents with their citation IDs."""
    return _search("precedent", query, tool_context)


def years_since(date: str) -> dict:
    """Return the number of years between a past date (YYYY-MM or YYYY-MM-DD) and today."""
    try:
        parts = [int(p) for p in date.split("-")]
        start = dt.date(parts[0], parts[1], parts[2] if len(parts) > 2 else 1)
    except (ValueError, IndexError):
        return {"error": "date must be YYYY-MM or YYYY-MM-DD"}
    days = (dt.date.today() - start).days
    if days < 0:
        return {"error": "date is in the future"}
    return {"years": round(days / 365.25, 1)}


INSTRUCTION = (
    "You are the Research agent in an underwriting evidence system. "
    "Read the case notes and do three things. "
    "1. Extract the case factors. Use only facts stated in the notes. "
    "Omit any field the notes do not state. Never estimate or guess. "
    "2. For any treatment or event date, call years_since. "
    "Never calculate a duration yourself. "
    "3. Call search_guidance and search_precedent at least once each, "
    "using the condition and its key facts as the query. "
    "The condition must be one of: " + ", ".join(sorted(RULES)) + ". "
    "For any other condition use a short snake_case name of your own. "
    "Occupation, if stated, must be one of: " + ", ".join(sorted(OCCUPATION)) + "; "
    "otherwise omit it. "
    "Cite only citation IDs that a search tool returned. Never invent an ID. "
    "Your final answer is one JSON object and nothing else, no prose and no code fence. "
    "It has two keys: factors (an object) and citations (a list of ID strings). "
    "Inside factors, condition is required. The optional fields are: "
    "years_since_treatment (number), recurrence (true or false), "
    "surveillance_clear (true or false), systolic (integer), diastolic (integer), "
    "medications (integer), stress_test_normal (true or false), hba1c (number), "
    "complications (integer), occupation (text), sum_assured (number in EUR)."
)

root_agent = Agent(
    name="research",
    model=config.LLM_MODEL,
    description=(
        "Extracts underwriting factors from case notes and finds the supporting "
        "guidance and precedent passages, returning citation IDs only."
    ),
    instruction=INSTRUCTION,
    tools=[search_guidance, search_precedent, years_since],
)
