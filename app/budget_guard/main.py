import base64
import json
import logging
import os

import functions_framework
import google.auth
from googleapiclient import discovery

PROJECT_ID = os.environ["PROJECT_ID"]
BUDGET_NAME = os.environ.get("BUDGET_NAME", "lumen-cap")
PAUSED_API = "aiplatform.googleapis.com"

logging.basicConfig(level=logging.INFO)


def _disable_vertex() -> None:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    service = discovery.build(
        "serviceusage", "v1", credentials=credentials, cache_discovery=False
    )
    name = f"projects/{PROJECT_ID}/services/{PAUSED_API}"
    service.services().disable(
        name=name, body={"disableDependentServices": False}
    ).execute()


@functions_framework.cloud_event
def pause_vertex(cloud_event):
    message = cloud_event.data["message"]
    payload = json.loads(base64.b64decode(message["data"]).decode("utf-8"))

    if payload.get("budgetDisplayName") != BUDGET_NAME:
        logging.info("ignored: message is for another budget")
        return

    cost = float(payload.get("costAmount", 0))
    limit = float(payload.get("budgetAmount", 0))
    logging.info("budget=%s cost=%.4f limit=%.4f", BUDGET_NAME, cost, limit)

    if limit <= 0 or cost < limit:
        logging.info("under budget: no action")
        return

    _disable_vertex()
    logging.warning("CAP REACHED: %s disabled for %s", PAUSED_API, PROJECT_ID)
