import sys

from google import genai
from google.genai import types

PROJECT_ID = "lumen-poc-srao26"
LOCATION = "us-east1"

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def list_models() -> None:
    for m in client.models.list(config={"query_base": True}):
        name = m.name or ""
        if "gemini" in name or "embedding" in name:
            print(name)


def call(model: str) -> None:
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


def embed(model: str) -> None:
    resp = client.models.embed_content(
        model=model, contents=["post-treatment mortality loading"]
    )
    print("dimensions:", len(resp.embeddings[0].values))


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "list":
        list_models()
    elif action == "call":
        call(sys.argv[2])
    elif action == "embed":
        embed(sys.argv[2])
