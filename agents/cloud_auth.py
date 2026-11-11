"""ID-token authentication for calling private Cloud Run services."""
import subprocess
import time
from urllib.parse import urlparse

import httpx

TOKEN_TTL = 50 * 60  # Google ID tokens last 60 minutes; refresh a little early
CALL_TIMEOUT = 300  # matches the Cloud Run request timeout of the agents


def audience_for(url):
    """Cloud Run wants the bare service URL as the token audience."""
    parts = urlparse(url)
    return parts.scheme + "://" + parts.hostname


def default_token_provider(audience):
    """Cloud Run: the metadata server. Laptop: your own gcloud login."""
    try:
        import google.auth.transport.requests
        from google.oauth2 import id_token

        return id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)
    except Exception as first:
        try:
            out = subprocess.run(
                ["gcloud", "auth", "print-identity-token"],
                capture_output=True, text=True, check=True,
            )
            return out.stdout.strip()
        except Exception as second:
            raise RuntimeError("could not get an ID token: " + str(second)) from first


class IdTokenAuth(httpx.Auth):
    """Adds a Bearer ID token to every request, cached until shortly before expiry."""

    def __init__(self, audience, provider=default_token_provider, clock=time.monotonic):
        self.audience = audience
        self._provider = provider
        self._clock = clock
        self._token = None
        self._expires = 0.0

    def token(self):
        if self._token is None or self._clock() >= self._expires:
            self._token = self._provider(self.audience)
            self._expires = self._clock() + TOKEN_TTL
        return self._token

    def auth_flow(self, request):
        request.headers["Authorization"] = "Bearer " + self.token()
        yield request


def authed_client(base_url, provider=default_token_provider):
    """An HTTP client that signs requests for a Cloud Run URL; None for localhost."""
    if urlparse(base_url).hostname in ("localhost", "127.0.0.1"):
        return None
    auth = IdTokenAuth(audience_for(base_url), provider=provider)
    return httpx.AsyncClient(auth=auth, timeout=CALL_TIMEOUT)
