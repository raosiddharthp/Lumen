from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent

from app.common import config
from app.common.llm import configure_vertex

configure_vertex()

agent = Agent(
    name="smoke",
    model=config.LLM_MODEL,
    description="Smoke-test agent that replies pong.",
    instruction="Reply with the single word: pong",
)

a2a_app = to_a2a(agent, port=8001)
