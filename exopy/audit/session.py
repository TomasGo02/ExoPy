from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class UserSession:
    """Minimal user context for traceable ExoPy operations."""

    username: str
    run_id: str = field(default_factory=lambda: uuid4().hex)


def login(username: str) -> UserSession:
    """Create a lightweight user session for auditable operations."""
    normalized = username.strip()
    if not normalized:
        msg = "username must not be empty"
        raise ValueError(msg)
    return UserSession(username=normalized)


class AuditLogger:
    """Write structured JSON-lines events for reproducibility and audit."""

    def __init__(self, path: Path | str | None = None, session: UserSession | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.session = session or UserSession(username="anonymous")
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event_type: str, **payload: Any) -> dict[str, Any]:
        """Append one event and return the serializable event dictionary."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "username": self.session.username,
            "run_id": self.session.run_id,
            "payload": _jsonable(payload),
        }
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def export(self, destination: Path | str) -> Path:
        """Copy the event log to a destination for replication or audit."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.path is None or not self.path.exists():
            destination.write_text("", encoding="utf-8")
        else:
            destination.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")
        return destination


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
