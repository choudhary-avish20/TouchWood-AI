"""
state_merge.py — deterministic fold of an extracted RoomState delta
into the running session RoomState.

Why code, not LLM:
  Merging structured state is a deterministic problem — scalar override,
  list union, dedup. Adding an LLM here would add latency and cost for
  zero benefit. The LLM's job (extraction) ends at producing the delta;
  the code's job starts at integrating it.

Merge rules by field type:
  Scalars   (room_type, width_cm, length_cm, style_text, budget_total)
            → delta value wins when it's not None (newer info overrides)
  Lists     (style_tags, existing_items)
            → ordered union: keep existing order, append new entries only
  item_requests
            → append new requests; deduplicate against existing ones by
              fuzzy-matching raw_phrase (see _is_duplicate_request).
              Never drops an existing request — only the incoming delta's
              requests are filtered.
"""

from __future__ import annotations

from extraction.schema import ItemRequest, RoomState

# Deduplication threshold for item_requests.
# Two requests are considered the same if their normalised raw_phrases
# share this many tokens as a fraction of the shorter phrase.
# 0.6 catches "a lamp" vs "some kind of lamp" while keeping
# "floor lamp" vs "desk lamp" separate.
_PHRASE_SIMILARITY_THRESHOLD = 0.6


def _normalise(phrase: str) -> set[str]:
    """Lowercase word-token set, strips punctuation."""
    import re
    return set(re.findall(r"[a-z]+", phrase.lower()))


def _is_duplicate_request(incoming: ItemRequest, existing: ItemRequest) -> bool:
    """True if `incoming` is close enough to `existing` that adding it
    would be redundant. Operates on raw_phrase only — categories may
    differ if extraction was inconsistent across turns."""
    if not incoming.raw_phrase or not existing.raw_phrase:
        return False
    a = _normalise(incoming.raw_phrase)
    b = _normalise(existing.raw_phrase)
    if not a or not b:
        return False
    overlap = len(a & b) / len(a | b)  # Jaccard similarity
    return overlap >= _PHRASE_SIMILARITY_THRESHOLD


def _merge_lists(existing: list, incoming: list) -> list:
    """Ordered union: keep existing order, append novel entries only."""
    seen = set(existing)
    result = list(existing)
    for item in incoming:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _merge_item_requests(
    existing: list[ItemRequest],
    incoming: list[ItemRequest],
) -> list[ItemRequest]:
    result = list(existing)
    for new_req in incoming:
        is_dup = any(_is_duplicate_request(new_req, ex) for ex in result)
        if not is_dup:
            result.append(new_req)
    return result


def merge(current: RoomState, delta: RoomState) -> RoomState:
    return RoomState(
        room_type=delta.room_type if delta.room_type is not None else current.room_type,
        width_cm=delta.width_cm if delta.width_cm is not None else current.width_cm,
        length_cm=delta.length_cm if delta.length_cm is not None else current.length_cm,
        style_text=delta.style_text if delta.style_text is not None else current.style_text,
        budget_total=delta.budget_total if delta.budget_total is not None else current.budget_total,

        existing_items=_merge_lists(current.existing_items, delta.existing_items),
        style_tags=_merge_lists(current.style_tags, delta.style_tags),

        item_requests=_merge_item_requests(current.item_requests, delta.item_requests),
    )


def clear_fulfilled_requests(
    state: RoomState,
    fulfilled_raw_phrases: list[str],
) -> RoomState:
    """
    Drops item_requests that have already been fulfilled (i.e. the
    recommender has surfaced results for them). Call this after each
    recommendation round so those requests don't keep triggering
    retrieval on subsequent turns.

    Args:
        state:                 The current session RoomState.
        fulfilled_raw_phrases: raw_phrase values of requests that have
                               been recommended for this turn.
    """
    fulfilled_normalised = [_normalise(p) for p in fulfilled_raw_phrases]

    def _is_fulfilled(req: ItemRequest) -> bool:
        req_tokens = _normalise(req.raw_phrase)
        for fn in fulfilled_normalised:
            if not req_tokens or not fn:
                continue
            if len(req_tokens & fn) / len(req_tokens | fn) >= _PHRASE_SIMILARITY_THRESHOLD:
                return True
        return False

    remaining = [r for r in state.item_requests if not _is_fulfilled(r)]
    return state.model_copy(update={"item_requests": remaining})


if __name__ == "__main__":
    from extraction.schema import ItemRequest, RoomState

    turn_1 = RoomState(
        room_type="bedroom",
        width_cm=304.8,
        length_cm=365.8,
        existing_items=["queen bed", "wooden desk"],
        style_tags=["minimalist"],
        style_text="warm and cozy",
        item_requests=[
            ItemRequest(raw_phrase="a rug", max_price=500.0),
            ItemRequest(raw_phrase="a lamp"),
        ],
    )

    turn_2_delta = RoomState(
        budget_total=2000.0,
        style_tags=["scandinavian"],
        existing_items=["queen bed"],
        item_requests=[
            ItemRequest(raw_phrase="some kind of lamp"),
            ItemRequest(raw_phrase="a vase for the shelf"),
        ],
    )

    merged = merge(turn_1, turn_2_delta)

    print("=== merged state ===")
    print(merged.model_dump_json(indent=2))

    print("\n=== after fulfilling 'a rug' ===")
    after = clear_fulfilled_requests(merged, fulfilled_raw_phrases=["a rug"])
    for r in after.item_requests:
        print(" -", r.raw_phrase)