"""
Extraction layer — calls a local Ollama model to turn a user's free-text
room description into a RoomState delta (Pydantic-validated JSON).
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
    return "qwen2.5:1.5b"


MODEL_NAME = resolve_model_name()

SYSTEM_PROMPT = f"""You extract structured information from a user's description of their living space.

Respond with ONLY a single JSON object, nothing else. No preamble, no
explanation, no markdown formatting. Use this exact shape:

{{
  "room_type": string or null,
  "width_cm": number or null,
  "length_cm": number or null,
  "existing_items": [string, ...],
  "placed_items": [
    {{
      "name": string,
      "wall": "north" | "south" | "east" | "west" | null,
      "corner": "north-east" | "north-west" | "south-east" | "south-west" | null,
      "raw_hint": string
    }}
  ],
  "style_tags": [string, ...],
  "style_text": string or null,
  "budget_total": number or null,
  "item_requests": [
    {{"raw_phrase": string, "max_price": number or null, "min_price": number or null}}
  ]
}}

Rules:
- Only include fields the user actually mentioned or implied. Use null
  or empty lists for anything not mentioned — never guess or invent values.
- Convert any stated dimensions to centimeters (e.g. "10 feet" -> 304.8).
- existing_items: ALL furniture/items already in the room as a flat list
  of lowercase strings. Always populate this regardless of placement info.
- placed_items: ONLY items where the user explicitly described their
  position. Each entry must also appear in existing_items.
  - wall: use cardinal direction. Map "top wall" → "north", "right wall"
    → "east", "bottom wall" → "south", "left wall" → "west". If the user
    says "against the window wall" without a direction, omit wall.
  - corner: use only when the user explicitly says "corner" or equivalent.
    Infer direction from context ("north-east corner" or "top-right corner"
    → "north-east").
  - raw_hint: copy the user's exact spatial phrase verbatim.
  - If no placement info is given for any item, placed_items should be [].
- style_tags must be EMPTY ([]) unless the user explicitly uses a style "
    "word or phrase — e.g. 'minimalist', 'boho', 'modern', 'cozy and rustic'. "
    "Do NOT infer style from furniture types or room layout. If the user says "
    "'I have a sofa and a TV' with no style mention, style_tags must be []. "
    "Same rule applies to style_text — null if no descriptive language was used."
  fit: {", ".join(ALLOWED_STYLE_TAGS)}. If nothing fits, use [].
- style_text: capture the user's own mood/descriptive language.
- item_requests: one entry per distinct thing the user wants recommended.
  If they didn't ask for anything, use [].
"- room_type: null unless the user explicitly names the room type. "
"Do NOT infer it from furniture (a sofa does not mean 'living room')."
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`\n ")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _extract_json_object(text: str) -> dict | None:
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
    On any failure returns an empty RoomState — a failed extraction on
    one turn shouldn't crash the conversation.
    """
    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={
                "model": MODEL_NAME,
                "system": SYSTEM_PROMPT,
                "prompt": user_text,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
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
            print(f"  [extraction failed: could not parse JSON]")
            return RoomState()

        # Defensive filtering on style_tags
        if isinstance(data.get("style_tags"), list):
            data["style_tags"] = [t for t in data["style_tags"] if t in ALLOWED_STYLE_TAGS][:3]

        # Ensure every placed_item name also appears in existing_items
        if isinstance(data.get("placed_items"), list) and isinstance(data.get("existing_items"), list):
            placed_names = {p.get("name", "").lower() for p in data["placed_items"]}
            existing_lower = {e.lower() for e in data["existing_items"]}
            missing = placed_names - existing_lower
            for name in missing:
                data["existing_items"].append(name)

        try:
            return RoomState.model_validate(data)
        except ValidationError as e:
            print(f"  [extraction validation failed: {e}]")
            return RoomState()

    except Exception as e:
        print(f"  [extraction call failed: {e}]")
        return RoomState()


if __name__ == "__main__":
    samples = [
        # Basic — no placement info
        "I have a small bedroom, about 12 by 10 feet, with a queen bed and a "
        "wooden desk. Going for something minimalist. Looking for a rug under £500.",

        # With placement info
        "My living room is 5 by 4 metres. The sofa is against the south wall, "
        "and the TV unit is on the east wall. There's a coffee table in the centre. "
        "I want something bohemian, maybe some cushions.",
    ]
    for sample in samples:
        print(f"\nInput: {sample[:60]}...")
        state = extract_room_state(sample)
        print(state.model_dump_json(indent=2))