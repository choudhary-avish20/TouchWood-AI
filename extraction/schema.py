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
        description="The user's own words for this item, e.g. 'something for the corner by the window' — kept for the recommendation step's context, not used for filtering.",
    )
    max_price: float | None = None
    min_price: float | None = None


class RoomState(BaseModel):
    """Persistent, accumulating state for the session — see the rolling
    state-merge pattern. Extraction produces a *delta* shaped like this;
    state_merge.py folds it into the running state in code, not via the LLM.
    """

    room_type: str | None = None                     # e.g. "bedroom", "living room"
    width_cm: float | None = None                     # room dimensions, not item dimensions
    length_cm: float | None = None
    existing_items: list[str] = Field(default_factory=list)   # e.g. ["queen bed", "wooden desk"]
    style_tags: list[str] = Field(default_factory=list)       # constrained to tagger.ALLOWED_STYLE_TAGS at validation time
    style_text: str | None = None                     # free-form theme description, e.g. "cozy, warm, a bit rustic"
    budget_total: float | None = None                 # overall budget, distinct from per-item max_price
    item_requests: list[ItemRequest] = Field(default_factory=list)

    class Config:
        extra = "ignore"  # tolerate the model emitting unexpected keys rather than failing validation