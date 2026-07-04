"""
FastAPI router wiring the full per-turn pipeline. binds all codes

flow: IMP
  1. Get or create session (session_id from request header or body)
  2. Extract RoomState delta from user message (local llm used heer)
  3. Merge delta into session RoomState
  4. For each item_request: map raw_phrase to categories, build RetrievalQuery, retrieve candidates
  5. Call recommender (big api llm) with all shortlists + room_state
  6. Clear fulfilled item_requests from session state
  7. Return { session_id, response, room_state }
    also, room_state is what the frontend uses to render the sketch, roomstate updates after every turn, so does the sketch
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.catalog_mapper import map_to_categories
from app.session import store
from config import RETRIEVAL_TOP_K
from extraction.extractor import extract_room_state
from extraction.schema import ItemRequest
from extraction.state_merge import clear_fulfilled_requests, merge
from recommendation.Recommender import recommend
from retrieval.retrieval import RetrievalQuery, RetrievedItem, retrieve

router = APIRouter()


# Request / response models
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    room_state: dict


# Helpers
def _build_retrieval_query(
    req: ItemRequest,
    room_state,
) -> RetrievalQuery:
    """Converts a single ItemRequest + session RoomState into a RetrievalQuery."""
    categories = req.categories or map_to_categories(req.raw_phrase)

    # fix budget fro per item
    max_price = req.max_price or room_state.budget_total

    return RetrievalQuery(
        categories=categories if categories else None,
        max_price=max_price,
        min_price=req.min_price,
        style_tags=room_state.style_tags,
        style_text=room_state.style_text,
        max_width_cm=room_state.width_cm,
    )


def _has_item_requests(room_state) -> bool:
    return bool(room_state.item_requests)


# Routes
@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    x_session_id: str | None = Header(default=None),
) -> ChatResponse:
    """
    Main chat endpoint. Accepts a user message and optional session_id
    (via body or X-Session-Id header — body takes priority).

    Always returns:
      - session_id: pass back on subsequent turns
      - response:   the recommendation or conversational reply
      - room_state: current structured state — frontend uses this to
                    re-render the room sketch on every turn
    """
    sid_input = body.session_id or x_session_id
    session_id, session = store.get_or_create(sid_input)

    #here start the steps mentioned at the top
    # 1. Extract delta
    delta = extract_room_state(body.message)

    # 2. Merge into session state
    session.room_state = merge(session.room_state, delta)

    # 3. Retrieve candidates for each active item_request
    shortlists: list[tuple[ItemRequest, list[RetrievedItem]]] = []

    if _has_item_requests(session.room_state):
        for req in session.room_state.item_requests:
            query = _build_retrieval_query(req, session.room_state)
            candidates = retrieve(query, top_k=RETRIEVAL_TOP_K)
            shortlists.append((req, candidates))
    # If no item_requests, shortlists is empty — recommender will handle
    # this as a conversational/follow-up turn rather than a product turn.

    # 4. Recommend
    response_text = recommend(
        state=session.room_state,
        shortlists=shortlists,
        user_text=body.message,
        conversation_history=session.history,
    )

    # 5. Clear fulfilled requests + update history
    fulfilled_phrases = [req.raw_phrase for req, _ in shortlists if _]
    session.room_state = clear_fulfilled_requests(
        session.room_state, fulfilled_phrases
    )
    session.add_turn(body.message, response_text)

    return ChatResponse(
        session_id=session_id,
        response=response_text,
        room_state=session.room_state.model_dump(),
    )


@router.get("/session/{session_id}/state")
async def get_state(session_id: str) -> dict:
    """
    Returns the current RoomState for a session.
    Useful for the frontend to restore the sketch on page reload
    without sending a new chat message.
    """
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    return session.room_state.model_dump()


@router.delete("/session/{session_id}")
async def end_session(session_id: str) -> dict:
    """Explicitly clears a session (e.g. user clicks 'Start over')."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    store._sessions.pop(session_id, None)
    return {"detail": "Session ended."}