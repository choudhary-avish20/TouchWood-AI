"""
storing the session. used mainly for context windows

"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from config import SESSION_TTL_SECONDS
from extraction.schema import RoomState


@dataclass
class Session:
    room_state: RoomState = field(default_factory=RoomState)
    # only last 4 mesasges turns kept for context.
    history: list[dict] = field(default_factory=list)
    last_active: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_active = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > SESSION_TTL_SECONDS

    def add_turn(self, user_text: str, assistant_text: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})
        # Keep only the last 4 messages
        self.history = self.history[-4:]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def _evict_expired(self) -> None:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
        for sid in expired:
            del self._sessions[sid]

    def create(self) -> tuple[str, Session]:
        """Creates a new session and returns (session_id, session)."""
        self._evict_expired()
        sid = str(uuid.uuid4())
        session = Session()
        self._sessions[sid] = session
        return sid, session

    def get(self, session_id: str) -> Session | None:
        """Returns the session if it exists and is not expired."""
        self._evict_expired()
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            del self._sessions[session_id]
            return None
        session.touch()
        return session

    def get_or_create(self, session_id: str | None) -> tuple[str, Session]:
        """Returns existing session or creates a new one."""
        if session_id:
            session = self.get(session_id)
            if session:
                return session_id, session
        return self.create()

store = SessionStore()