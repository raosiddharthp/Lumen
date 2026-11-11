from google.adk.a2a.utils.agent_to_a2a import to_a2a

from agents.gate.agent import root_agent
from app.common.a2a_url import card_origin

a2a_app = to_a2a(root_agent, **card_origin(8012))
