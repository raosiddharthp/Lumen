"""Where an A2A agent says it can be reached (the URL in its Agent Card)."""
import os
from urllib.parse import urlparse


def card_origin(default_port, env=None):
    """Return the host, port and protocol to advertise in the Agent Card.

    PUBLIC_URL unset: localhost on the dev port (laptop).
    PUBLIC_URL set: that URL (Cloud Run), with the default port for its scheme.
    """
    env = os.environ if env is None else env
    url = env.get("PUBLIC_URL")
    if not url:
        return {"host": "localhost", "port": default_port, "protocol": "http"}
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("PUBLIC_URL must look like https://host, got: " + url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return {"host": parts.hostname, "port": port, "protocol": parts.scheme}
