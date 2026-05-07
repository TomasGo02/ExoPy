from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Instrument:
    """Instrument selector used for DACE queries and local grouping."""

    name: str
    version: str | None = None
    mode: str | None = None
    drs_version: str = "latest"

    @property
    def dace_name(self) -> str:
        """Return the instrument name as DACE expects it."""
        if self.version and not self.name.endswith(self.version):
            return f"{self.name}{self.version}"
        return self.name

    @property
    def group(self) -> str:
        """Return the broader instrument family."""
        return self.name

    def as_filters(self) -> dict[str, dict[str, list[str]]]:
        """Build DACE-compatible filters for this instrument."""
        filters: dict[str, dict[str, list[str]]] = {
            "instrument_name": {"equals": [self.dace_name]},
        }
        if self.mode:
            filters["instrument_mode"] = {"equals": [self.mode]}
        return filters
