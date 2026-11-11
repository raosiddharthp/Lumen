from agents.remote_agents import RemoteTransport, agent_urls, cloud_urls
from app.common import config


def test_cloud_urls_follow_the_cloud_run_pattern():
    assert cloud_urls("123", "us-east1") == {
        "research": "https://lumen-research-123.us-east1.run.app",
        "gate": "https://lumen-gate-123.us-east1.run.app",
        "drafting": "https://lumen-drafting-123.us-east1.run.app",
    }


def test_local_is_the_default():
    assert agent_urls({}) == {
        "research": "http://localhost:8011",
        "gate": "http://localhost:8012",
        "drafting": "http://localhost:8013",
    }


def test_cloud_is_chosen_by_the_environment():
    got = agent_urls({"LUMEN_AGENTS": "cloud"})
    assert got == cloud_urls(config.PROJECT_NUMBER, config.AGENT_REGION)


def test_an_explicit_host_is_still_honoured():
    assert agent_urls({}, host="http://10.0.0.5")["gate"] == "http://10.0.0.5:8012"


def test_the_transport_normalises_a_trailing_slash():
    transport = RemoteTransport("https://a.example/", "x")
    assert transport.base_url == "https://a.example"
    assert transport.card.startswith("https://a.example/.well-known/")
