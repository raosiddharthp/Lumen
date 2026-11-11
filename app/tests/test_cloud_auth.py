import asyncio

import httpx

from agents import cloud_auth
from agents.cloud_auth import IdTokenAuth, audience_for, authed_client


def test_the_audience_is_the_bare_service_url():
    url = "https://lumen-x-1.us-east1.run.app:443/a/b"
    assert audience_for(url) == "https://lumen-x-1.us-east1.run.app"


def test_a_token_is_fetched_once_and_reused():
    calls = []

    def provider(audience):
        calls.append(audience)
        return "tok"

    auth = IdTokenAuth("https://a.example", provider=provider, clock=lambda: 0.0)
    assert auth.token() == "tok" and auth.token() == "tok"
    assert calls == ["https://a.example"]


def test_a_token_is_refreshed_after_the_ttl():
    now = [0.0]
    calls = []

    def provider(audience):
        calls.append(audience)
        return "t" + str(len(calls))

    auth = IdTokenAuth("https://a.example", provider=provider, clock=lambda: now[0])
    assert auth.token() == "t1"
    now[0] = cloud_auth.TOKEN_TTL + 1
    assert auth.token() == "t2"


def test_the_bearer_header_is_attached_to_requests():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200)

    auth = IdTokenAuth("https://a.example", provider=lambda audience: "tok")
    with httpx.Client(transport=httpx.MockTransport(handler), auth=auth) as client:
        client.get("https://a.example/x")
    assert seen["auth"] == "Bearer tok"


def test_localhost_needs_no_special_client():
    assert authed_client("http://localhost:8011") is None


def test_a_cloud_url_gets_an_authenticated_client():
    client = authed_client("https://a.example:443", provider=lambda audience: "tok")
    assert isinstance(client.auth, IdTokenAuth)
    assert client.auth.audience == "https://a.example"
    asyncio.run(client.aclose())
