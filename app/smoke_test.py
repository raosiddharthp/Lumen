import sys

from google import genai
from google.genai import types

PROJECT_ID = "lumen-poc-srao26"
DEFAULT_LOCATION = "us-east1"


def make_client(location: str) -> genai.Client:
    return genai.Client(vertexai=True, project=PROJECT_ID, location=location)


def list_models(location: str) -> None:
    client = make_client(location)
    for m in client.models.list(config={"query_base": True}):
        name = m.name or ""
        if "gemini" in name or "embedding" in name:
            print(name)


def call(model: str, location: str) -> None:
    client = make_client(location)
    resp = client.models.generate_content(
        model=model,
        contents="Reply with the single word: ready",
        config=types.GenerateContentConfig(max_output_tokens=64, temperature=0),
    )
    usage = resp.usage_metadata
    print("text:", resp.text)
    print("prompt_tokens:", usage.prompt_token_count)
    print("output_tokens:", usage.candidates_token_count)
    print("thinking_tokens:", getattr(usage, "thoughts_token_count", None))


def embed(model: str, location: str) -> None:
    client = make_client(location)
    resp = client.models.embed_content(
        model=model, contents=["post-treatment mortality loading"]
    )
    print("dimensions:", len(resp.embeddings[0].values))


if __name__ == "__main__":
    action = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else ""
    loc = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_LOCATION
    if action == "list":
        list_models(loc)
    elif action == "call":
        call(model, loc)
    elif action == "embed":
        embed(model, loc)
