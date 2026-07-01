"""
Extraction layer — calls a local Ollama model to turn a user's free-text
room description into a RoomState delta (Pydantic-validated JSON).

This mirrors catalog/tagger.py's call pattern deliberately (same Ollama
endpoint, same defensive JSON parsing) since both are "small structured
extraction" jobs running on the same local model.

Returns a *delta*, not the full session state — state_merge.py is
responsible for folding this into the running RoomState in code.
"""

import json
import os
import re

import requests
from pydantic import ValidationError

from extraction.schema import RoomState

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"

# Kept in sync with catalog/tagger.py's vocabulary — style tags need to
# mean the same thing whether they're attached to a catalog item or to
# a user's request, or semantic matching in retrieval breaks down.
ALLOWED_STYLE_TAGS = [
    "minimalist", "scandinavian", "mid-century", "rustic", "bohemian",
    "industrial", "modern", "traditional", "coastal", "glam",
    "farmhouse", "japandi", "art-deco", "eclectic",
]


def resolve_model_name() -> str:
    preferred = os.getenv("OLLAMA_MODEL")
    if preferred:
        return preferred
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        names = [m.get("name") for m in models if m.get("name")]
        if names:
            return names[0]
    except Exception:
        pass
    return "llama3:8b"


MODEL_NAME = resolve_model_name()

SYSTEM_PROMPT = f"""You extract structured information from a user's description of their living space.

Respond with ONLY a single JSON object, nothing else. No preamble, no
explanation, no markdown formatting. Use this exact shape:

{{
  "room_type": string or null,
  "width_cm": number or null,
  "length_cm": number or null,
  "existing_items": [string, ...],
  "style_tags": [string, ...],
  "style_text": string or null,
  "budget_total": number or null,
  "item_requests": [
    {{"raw_phrase": string, "max_price": number or null, "min_price": number or null}}
  ]
}}

Rules:
- Only include fields the user actually mentioned or implied. Use null
  or an empty list for anything not mentioned — never guess or invent
  values (e.g. don't assume a budget if none was stated).
- Convert any stated dimensions to centimeters (e.g. "10 feet" -> 304.8).
- style_tags must ONLY contain values from this exact list, choose 0-3
  that fit: {", ".join(ALLOWED_STYLE_TAGS)}. If nothing fits, use [].
- style_text should capture the user's own descriptive/mood language
  (e.g. "cozy, a bit rustic") even if it doesn't map to a style_tag.
- item_requests: one entry per distinct thing the user wants
  recommendations for. If they didn't ask for anything specific yet,
  use an empty list.
- existing_items: furniture/items already in the room, not things
  being requested.
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`\n ")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _extract_json_object(text: str) -> dict | None:
    """Best-effort JSON object extraction from a response that may
    include stray text around the JSON despite instructions."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def extract_room_state(user_text: str) -> RoomState:
    """
    Calls the local Ollama model and returns a validated RoomState delta.
    On any failure (connection error, malformed JSON, validation error),
    returns an empty RoomState rather than raising — a failed extraction
    on one turn shouldn't crash the conversation; the caller just gets
    no new information to merge that turn.
    """
    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": MODEL_NAME,
                "system": SYSTEM_PROMPT,
                "prompt": user_text,
                "stream": False,
                "format": "json",  # ask Ollama to constrain output to valid JSON where supported
                "options": {"temperature": 0.1},  # low temp: extraction wants consistency, not creativity
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("error"):
            raise RuntimeError(payload["error"])

        raw_output = payload.get("response", "")
        if not isinstance(raw_output, str):
            return RoomState()

        cleaned = _strip_code_fence(raw_output)
        data = _extract_json_object(cleaned)
        if data is None:
            print(f"  [extraction failed: could not parse JSON from model output]")
            return RoomState()

        # Defensive filtering on style_tags before validation, in case
        # the model drifts outside the allowed vocabulary despite
        # instructions — same pattern as tagger.py.
        if isinstance(data.get("style_tags"), list):
            data["style_tags"] = [t for t in data["style_tags"] if t in ALLOWED_STYLE_TAGS][:3]

        try:
            return RoomState.model_validate(data)
        except ValidationError as e:
            print(f"  [extraction validation failed: {e}]")
            return RoomState()

    except Exception as e:
        print(f"  [extraction call failed: {e}]")
        return RoomState()


if __name__ == "__main__":
    sample = (
        "I have a small bedroom, about 12 by 10 feet, with a queen bed and a "
        "wooden desk already in there. I'm going for something minimalist and "
        "warm. Looking for a rug under $50 and maybe a nice lamp."
    )
    state = extract_room_state(sample)
    print(state.model_dump_json(indent=2))