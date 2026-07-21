"""
RoomState schema — the structured output of the extraction layer.

Designed to map almost 1:1 onto retrieval.RetrievalQuery, so building a
query from a RoomState (or one of its ItemRequests) is a near-direct
field copy, not a translation step.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ItemRequest(BaseModel):
    """One thing the user wants recommendations for, e.g. 'a rug' or
    'some kind of lighting'. A single user message can produce several
    of these ("need a vase and a rug") or just one.
    """

    categories: list[str] = Field(
        default_factory=list,
        description="Catalog category names this request maps to, e.g. ['Vases'] or ['Rugs', 'Carpets'].",
    )
    raw_phrase: str = Field(
        default="",
        description="The user's own words for this item — kept for recommendation context.",
    )
    max_price: float | None = None
    min_price: float | None = None


class PlacedItem(BaseModel):
    """An existing furniture item with optional spatial placement hints
    extracted from the user's description.

    Only wall and corner are extracted — these are the most reliably
    stated and most useful for sketch rendering. Full coordinates are
    never extracted; the sketch derives pixel positions from these hints.

    Examples of user text that populates these fields:
      "my bed is against the north wall"           → wall="north"
      "desk in the north-east corner"              → corner="north-east"
      "sofa on the south wall, desk to its right"  → wall="south", raw_hint preserved
    """

    name: str
    wall: str | None = Field(
        default=None,
        description="Wall the item is placed against: 'north' | 'south' | 'east' | 'west'. "
                    "Use cardinal directions or map top/right/bottom/left to north/east/south/west.",
    )
    corner: str | None = Field(
        default=None,
        description="Corner the item occupies: 'north-east' | 'north-west' | 'south-east' | 'south-west'.",
    )
    raw_hint: str = Field(
        default="",
        description="The user's verbatim spatial description — preserved for recommendation context.",
    )


class RoomState(BaseModel):
    """Persistent, accumulating state for the session — see the rolling
    state-merge pattern. Extraction produces a *delta* shaped like this;
    state_merge.py folds it into the running state in code, not via the LLM.
    """

    room_type: str | None = None
    width_cm: float | None = None
    length_cm: float | None = None

    # Flat list — always populated, used by retrieval and recommendation.
    existing_items: list[str] = Field(default_factory=list)

    # Spatial placement hints — populated only when the user describes
    # where furniture is. The sketch uses this first; falls back to
    # clockwise wall placement for any item not listed here.
    placed_items: list[PlacedItem] = Field(default_factory=list)

    style_tags: list[str] = Field(default_factory=list)
    style_text: str | None = None
    budget_total: float | None = None
    item_requests: list[ItemRequest] = Field(default_factory=list)

    class Config:
        extra = "ignore"