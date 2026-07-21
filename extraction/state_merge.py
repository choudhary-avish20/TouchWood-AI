"""
state_merge.py — deterministic fold of an extracted RoomState delta
into the running session RoomState.

Merge rules by field type:
    Scalars      → delta wins when not None
    Lists        → ordered union (existing_items, style_tags)
    placed_items → merge by name: update placement if item already known,
                    append if new. Never removes an existing entry.
    item_requests → append deduplicated new requests (Jaccard on raw_phrase)
"""

from __future__ import annotations

import re
from extraction.schema import ItemRequest, PlacedItem, RoomState

_PHRASE_SIMILARITY_THRESHOLD = 0.6


def _normalise(phrase: str) -> set[str]:
    return set(re.findall(r"[a-z]+", phrase.lower()))


def _is_duplicate_request(incoming: ItemRequest, existing: ItemRequest) -> bool:
    if not incoming.raw_phrase or not existing.raw_phrase:
        return False
    a = _normalise(incoming.raw_phrase)
    b = _normalise(existing.raw_phrase)
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= _PHRASE_SIMILARITY_THRESHOLD


def _merge_lists(existing: list, incoming: list) -> list:
    seen = set(existing)
    result = list(existing)
    for item in incoming:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _merge_placed_items(
    existing: list[PlacedItem],
    incoming: list[PlacedItem],
) -> list[PlacedItem]:
    """
    Merge strategy:
    - If an item with the same name already exists, update its placement
        fields with the incoming delta (newer info wins — the user just
        corrected or added detail).
    - If the name is new, append it.
    - Name matching is case-insensitive.
    """
    result = {p.name.lower(): p for p in existing}

    for new_item in incoming:
        key = new_item.name.lower()
        if key in result:
            existing_item = result[key]
            result[key] = PlacedItem(
                name=existing_item.name,
                wall=new_item.wall if new_item.wall is not None else existing_item.wall,
                corner=new_item.corner if new_item.corner is not None else existing_item.corner,
                raw_hint=new_item.raw_hint if new_item.raw_hint else existing_item.raw_hint,
            )
        else:
            result[key] = new_item

    return list(result.values())


def _merge_item_requests(
    existing: list[ItemRequest],
    incoming: list[ItemRequest],
) -> list[ItemRequest]:
    result = list(existing)
    for new_req in incoming:
        if not any(_is_duplicate_request(new_req, ex) for ex in result):
            result.append(new_req)
    return result


def merge(current: RoomState, delta: RoomState) -> RoomState:
    """
    Returns a new RoomState applying delta on top of current.
    Neither argument is mutated.
    """
    return RoomState(
        # Scalars: delta wins when not None
        room_type=delta.room_type if delta.room_type is not None else current.room_type,
        width_cm=delta.width_cm if delta.width_cm is not None else current.width_cm,
        length_cm=delta.length_cm if delta.length_cm is not None else current.length_cm,
        style_text=delta.style_text if delta.style_text is not None else current.style_text,
        budget_total=delta.budget_total if delta.budget_total is not None else current.budget_total,

        # Lists: ordered union
        existing_items=_merge_lists(current.existing_items, delta.existing_items),
        style_tags=_merge_lists(current.style_tags, delta.style_tags),

        # placed_items: update by name, append new
        placed_items=_merge_placed_items(current.placed_items, delta.placed_items),

        # item_requests: append deduplicated
        item_requests=_merge_item_requests(current.item_requests, delta.item_requests),
    )


def clear_fulfilled_requests(
    state: RoomState,
    fulfilled_raw_phrases: list[str],
) -> RoomState:
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


# ---------------------------------------------------------------------------
# Self-test — python -m extraction.state_merge
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from extraction.schema import ItemRequest, PlacedItem, RoomState

    turn_1 = RoomState(
        room_type="living room",
        width_cm=500,
        length_cm=400,
        existing_items=["sofa", "tv unit", "coffee table"],
        placed_items=[
            PlacedItem(name="sofa", wall="south", raw_hint="sofa against the south wall"),
            PlacedItem(name="tv unit", wall="north", raw_hint="tv unit on the north wall"),
        ],
        style_tags=["bohemian"],
        item_requests=[ItemRequest(raw_phrase="some cushions")],
    )

    # Turn 2: user clarifies coffee table position, adds a new item
    turn_2_delta = RoomState(
        existing_items=["coffee table", "bookshelf"],
        placed_items=[
            PlacedItem(name="coffee table", corner="south-west", raw_hint="coffee table in the south-west corner"),
            PlacedItem(name="bookshelf", wall="east", raw_hint="bookshelf on the east wall"),
        ],
        style_tags=["eclectic"],
        item_requests=[
            ItemRequest(raw_phrase="some cushions"),   # dup — should be dropped
            ItemRequest(raw_phrase="a floor lamp"),    # new — should be added
        ],
    )

    merged = merge(turn_1, turn_2_delta)
    print("=== merged state ===")
    print(merged.model_dump_json(indent=2))