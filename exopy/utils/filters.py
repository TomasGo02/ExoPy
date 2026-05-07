from __future__ import annotations

from typing import Any


def equals_filter(field: str, *values: Any) -> dict[str, dict[str, list[Any]]]:
    """Build the common DACE equality filter shape."""
    return {field: {"equals": list(values)}}
