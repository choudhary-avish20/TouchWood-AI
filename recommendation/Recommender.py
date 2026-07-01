"""
recommender.py — hosted recommendation layer.

Takes the session RoomState and a list of (ItemRequest, [RetrievedItem])
pairs from the retrieval layer, calls Claude Haiku via the Anthropic API,
and returns the written recommendation.

Token budget per call:
  - System prompt:       ~400 tokens, cached after turn 1 (~10% cost)
  - Room state summary:  ~80–120 tokens
  - Candidate shortlist: ~60–80 tokens per item × up to 8 items × N requests
  - User message:        variable, typically 20–60 tokens
  - Max output:          600 tokens (enough for 2–3 recs per request)
"""

from __future__ import annotations

import os

import anthropic

from extraction.schema import ItemRequest, RoomState
from recommendation.prompts import build_system_payload
from retrieval.retrieval import RetrievedItem

MODEL = os.getenv("ANTHROPIC_RECOMMENDATION_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS = 600

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def _format_room_state(state: RoomState) -> str:
    """Compact, human-readable room summary sent in the user turn.
    Keeps tokens low while giving the model enough context to make
    room-specific recommendations.
    """
    lines: list[str] = []

    if state.room_type:
        line = f"Room: {state.room_type}"
        if state.width_cm and state.length_cm:
            line += f" ({state.width_cm:.0f} × {state.length_cm:.0f} cm)"
        lines.append(line)

    if state.existing_items:
        lines.append(f"Existing furniture: {', '.join(state.existing_items)}")

    style_parts: list[str] = []
    if state.style_tags:
        style_parts.append(", ".join(state.style_tags))
    if state.style_text:
        style_parts.append(state.style_text)
    if style_parts:
        lines.append(f"Style: {'; '.join(style_parts)}")

    if state.budget_total is not None:
        lines.append(f"Overall budget: {state.budget_total:.0f}")

    return "\n".join(lines) if lines else "No room details provided yet."


def _format_candidate(item: RetrievedItem) -> str:
    """Single-line summary of a retrieved catalog item. Concise by design —
    the model only needs enough to identify and discuss the product."""
    parts = [f"- {item.name}"]

    if item.price is not None:
        parts.append(f"{item.price:.0f} {item.currency}")

    dims: list[str] = []
    if item.width_cm:
        dims.append(f"W{item.width_cm:.0f}")
    if item.height_cm:
        dims.append(f"H{item.height_cm:.0f}")
    if item.depth_cm:
        dims.append(f"D{item.depth_cm:.0f}")
    if item.diameter_cm:
        dims.append(f"⌀{item.diameter_cm:.0f}")
    if dims:
        parts.append(f"[{' × '.join(dims)} cm]")

    if item.description:
        # Truncate long descriptions — the embedding already captured the
        # semantics; the model just needs enough to talk about the product.
        desc = item.description[:120].rstrip()
        if len(item.description) > 120:
            desc += "…"
        parts.append(f"— {desc}")

    if item.style_tags:
        parts.append(f"({', '.join(item.style_tags)})")

    return " ".join(parts)


def _build_user_message(
    state: RoomState,
    shortlists: list[tuple[ItemRequest, list[RetrievedItem]]],
    user_text: str,
) -> str:
    """Assembles the full dynamic user-turn content:
      room state summary + per-request candidate lists + the user's message.
    """
    sections: list[str] = []

    sections.append("## Room summary")
    sections.append(_format_room_state(state))

    for req, candidates in shortlists:
        label = req.raw_phrase or ", ".join(req.categories) or "item"
        sections.append(f"\n## Candidates for: {label}")
        if candidates:
            sections.extend(_format_candidate(c) for c in candidates)
        else:
            sections.append("(no matching products found in catalog)")

    sections.append(f"\n## User message\n{user_text}")

    return "\n".join(sections)

def recommend(
    state: RoomState,
    shortlists: list[tuple[ItemRequest, list[RetrievedItem]]],
    user_text: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Calls the hosted model and returns the recommendation text.

    Args:
        state:                 Current session RoomState (post-merge).
        shortlists:            List of (ItemRequest, candidates) pairs from
                               retrieval — one per active item_request.
        user_text:             The user's latest raw message, included so
                               the model can address follow-up questions
                               or nuances the structured state doesn't capture.
        conversation_history:  Optional list of prior {"role", "content"}
                               turns. Keep short (last 2–4 turns max) —
                               the room state summary already carries the
                               accumulated context, so full history isn't
                               needed and would waste tokens.

    Returns:
        The model's response as a plain string.

    Raises:
        anthropic.APIError subclasses on API failures — callers should
        handle these (retry, graceful degrade to local model, etc).
    """
    user_content = _build_user_message(state, shortlists, user_text)

    messages: list[dict] = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_content})

    response = _get_client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=build_system_payload(),   # cached after first call
        messages=messages,
    )

    return response.content[0].text

if __name__ == "__main__":
    from extraction.schema import ItemRequest, RoomState
    from retrieval.retrieval import RetrievedItem

    state = RoomState(
        room_type="bedroom",
        width_cm=304.8,
        length_cm=365.8,
        existing_items=["queen bed", "wooden desk"],
        style_tags=["minimalist", "scandinavian"],
        style_text="warm and cozy",
        budget_total=2000,
    )

    req = ItemRequest(raw_phrase="a rug", max_price=500)
    candidates = [
        RetrievedItem(
            id=1, name="Loom Wool Rug", category="Rugs", retailer="HomeStore",
            price=349, currency="INR", width_cm=160, height_cm=None,
            depth_cm=230, diameter_cm=None,
            description="Hand-loomed natural wool rug in oatmeal tones. Dense pile.",
            style_tags=["scandinavian", "minimalist"],
            image_url=None, source_url="https://example.com", score=0.91,
        ),
        RetrievedItem(
            id=2, name="Jute Flatweave", category="Rugs", retailer="Artisan Co",
            price=199, currency="INR", width_cm=150, height_cm=None,
            depth_cm=200, diameter_cm=None,
            description="Natural jute flatweave, earthy texture, reversible.",
            style_tags=["rustic", "minimalist"],
            image_url=None, source_url="https://example.com", score=0.84,
        ),
    ]

    result = recommend(
        state=state,
        shortlists=[(req, candidates)],
        user_text="I need a rug that won't make the room feel too heavy.",
    )
    print(result)