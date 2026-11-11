# Lumen: decisions and mistakes

A running log of design decisions and the mistakes that shaped them.

## Decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | Rating and Referral are deterministic modules inside the orchestrator, not A2A agents. | They must never be probabilistic. This is a deliberate deviation from "five agents". |
| D2 | Gemini on Vertex AI with service-account identity (ADC). No API keys, and `GOOGLE_API_KEY` is removed from the environment in code. | Keys leak. Identity does not. |
| D3 | Two-layer cost guard: a budget alert publishes to Pub/Sub, and a function disables the Vertex API (hard stop). App-side limits come in E8. | Budget alerts lag by hours, so the API itself is the backstop. Budget is 1.25 SGD. |
| D4 | Model and location live in config. Default is `gemini-3.1-flash-lite` on the `global` endpoint; embeddings are `gemini-embedding-001` at 768 dimensions, normalised. | Model retirements become config changes. |
| D5 | Embeddings stored in Firestore, cosine similarity computed in code, corpus cached per process. | No vector database to pay for at 20 documents. |
| D6 | The Referral Gate takes no confidence input and fails closed. Postponement is Tier 1. | A confidence shortcut would let the model decide who signs. |
| D7 | The event log is append-only by code (`create()`), with SHA-256 digests of inputs and outputs, and a failed log write fails the run. | An unlogged decision must not go out. Permission-level enforcement is a known gap. |
| D8 | Agents exchange citation IDs, not passage text. Trusted code fetches text from the corpus. | No agent can inject or misquote evidence. |
| D9 | The model never does date arithmetic. A `years_since` tool computes durations. | Models are unreliable at date maths, and the number feeds the rating. |
| D10 | The Grounding Gate has no tools. Case notes and the rating output are supplied as pseudo-passages `CASE` and `RATING`. A draft is a list of sentences, each with its own cites. | The Gate can check every sentence, including numbers, against trusted text. |
| D11 | The Gate model is a separate setting (`GATE_MODEL`). | The judge can be upgraded without code changes. |
| D12 | Research citations are never trusted raw. The Gate's applicability check decides which citations survive. | The agent cites everything it retrieves. |
| D13 | One image serves all agent services. An `APP` environment variable picks which agent each service runs. | Layers are stored once, which keeps the registry under its 0.5 GB free allowance. |
| D14 | The agent services are closed to the public. Only the orchestrator identity may call them, using a Google-signed ID token. | A stranger who finds an agent URL gets a 403 instead of spending Gemini tokens. IAM-denied requests are not billed. |
| D15 | One identity per agent with minimum roles. Only research and the orchestrator can read Firestore. | A compromised gate or drafting service cannot read stored cases. |
| D16 | Dependencies are installed from a frozen lock file taken from the environment that works. | Imports made inside libraries at startup are invisible to a static scan. The image must match what runs locally. |
| D17 | Each agent advertises its public address from `PUBLIC_URL`, and falls back to localhost. | The same code serves the laptop and Cloud Run. A card that says localhost is unreachable. |
| D18 | Token usage is not visible over A2A, so cost control moves server-side in E8. | Remote agents do not return usage, so the orchestrator reports zero. |

## Mistakes

| # | What happened | Fix |
|---|---------------|-----|
| M1 | An API key was exposed in screenshots. | Deleted and rotated. Secrets are never pasted or screenshotted. |
| M2 | A project was unlinked from billing to free a slot under the 5-project quota, and it hosted live apps. | Quota-increase request. Check what a project hosts before unlinking. |
| M3 | The budget amount `0.5SGD` was parsed as 5 nanos, effectively zero. | Nine-decimal nanos. Final budget 1.25 SGD. |
| M4 | Gemini 2.5 models were recommended but return 404 for new projects in every region. | Moved to `gemini-3.1-flash-lite` on `global`. |
| M5 | The budget function deploy failed for a missing Service Usage consumer role. | Granted the role and redeployed. |
| M6 | Heredocs and Python pasted into zsh hung the shell. | Heredocs start at column 0. Python goes in files. |
| M7 | The bare `uvicorn` command resolved to the system Python, not the venv. | Use `python -m uvicorn`. |
| M8 | A2A docs showed an older Agent Card shape than the installed `a2a-sdk` 1.3.0. | Check every A2A detail against the real card. |
| M9 | ADK treats `{name}` in an instruction as a template variable. | No curly braces in prompts. |
| M10 | The Gate prompt demanded exact numbers, so it rejected the best precedent (6 years against 6.7). | The tolerance is now stated inside the claim. |
| M11 | The Research agent cited all six passages it retrieved, including a stage II rule for a stage I case. | Added the applicability check (D12). |
| M12 | Private helpers are imported across modules (`passages.py`, `draft.py`). | Tidy in E7. |
| M13 | Two service accounts were created without first listing the existing ones. The project already had one per agent. | Removed the duplicates and used the existing four. List before creating. |
| M14 | The first deploy failed at startup. `google-cloud-firestore` was installed locally but never declared. | Pinned it. Compare declared dependencies with what the code imports. |
| M15 | The second deploy failed. `sse_starlette`, which `a2a-sdk` imports at startup, was missing. A static import scan could not see it. | Lock file (D16). Build from the environment that works, not from a hand-picked list. |
