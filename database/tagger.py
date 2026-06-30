"""
Uses a local Ollama model to generate style tags for catalog items, since
the source dataset has no explicit style/theme field (no "minimalist",
"mid-century", etc. column — we have to derive it from free text).
"""

import json
import os
import re

import requests

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"


def resolve_model_name() -> str:
    """Use the configured model when available, otherwise fall back to
    an installed model from the local Ollama server.
    """
    preferred = os.getenv("OLLAMA_MODEL")
    if preferred:
        return preferred

    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        names = [model.get("name") for model in models if model.get("name")]
        if names:
            return names[0]
    except Exception:
        pass

    return "llama3:8b"


MODEL_NAME = resolve_model_name()

ALLOWED_STYLE_TAGS = [
    "minimalist", "scandinavian", "mid-century", "rustic", "bohemian",
    "industrial", "modern", "traditional", "coastal", "glam",
    "farmhouse", "japandi", "art-deco", "eclectic",
]

SYSTEM_PROMPT = f"""You tag home decor products with style descriptors.
Given a product's name, description, and material, choose 1-3 tags ONLY
from this exact list: {", ".join(ALLOWED_STYLE_TAGS)}.

Respond with ONLY a JSON array of strings, nothing else. No preamble,
no explanation, no markdown formatting. Example output:
["minimalist", "scandinavian"]

If nothing fits well, respond with: []
"""


def generate_style_tags(name: str, description: str, material: str | None) -> list[str]:
    """
    Calls the local Ollama model to produce style tags for one item.
    Returns an empty list on any failure (malformed output, connection
    error, etc.) rather than raising — a missing tag shouldn't halt
    ingestion of an otherwise valid row.
    """
    prompt = (
        f"Product name: {name}\n"
        f"Description: {description or '(none)'}\n"
        f"Material: {material or '(none)'}"
    )

    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": MODEL_NAME,
                "system": SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1},  # low temp: we want consistent tagging, not creative variety
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("error"):
            raise RuntimeError(payload["error"])

        raw_output = payload.get("response", "")
        if not isinstance(raw_output, str):
            return []

        # Some models may wrap JSON in markdown or add surrounding text.
        raw_output = raw_output.strip()
        if raw_output.startswith("```"):
            raw_output = raw_output.strip("`\n ")

        # Try strict JSON first, then fall back to extracting a JSON array
        # from a response that includes a small amount of surrounding text.
        try:
            tags = json.loads(raw_output)
        except json.JSONDecodeError:
            match = re.search(r"\[[^\]]*\]", raw_output)
            if match:
                tags = json.loads(match.group(0))
            else:
                tags = None

        if isinstance(tags, dict):
            tags = [key for key in tags if key in ALLOWED_STYLE_TAGS]

        if not isinstance(tags, list):
            return []

        # Defensive filtering: only keep tags actually in our allowed
        # vocabulary, in case the model drifts despite instructions.
        return [t for t in tags if t in ALLOWED_STYLE_TAGS][:3]

    except Exception as e:
        print(f"  [style-tag generation failed for '{name}': {e}]")
        return []


if __name__ == "__main__":
    test_items = [
        {
            "name": "ADLAD",
            "description": "Scented candle in glass, Scandinavian Woods/white. "
                            "Comforting, familiar experience of Scandinavian forests "
                            "with spicy citrus notes.",
            "material": "Glass, Plant based wax",
        },
        {
            "name": "ALMARÖD",
            "description": "Mirror, black. Traditional matt black frame with a thin "
                            "golden line along the inner edge.",
            "material": "Fibreboard, Glass, Galvanized steel",
        },
    ]
    for item in test_items:
        tags = generate_style_tags(item["name"], item["description"], item["material"])
        print(f"{item['name']}: {tags}")
