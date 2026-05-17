from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from exopy.core.observation import Observation
from exopy.pipeline.processing import ObservationProcessor


@dataclass(slots=True)
class ObservationIndex:
    """In-memory index by object, instrument, and observation date."""

    records: list[dict[str, Any]] = field(default_factory=list)
    processor: ObservationProcessor = field(default_factory=ObservationProcessor)

    def add(self, observation: Observation) -> dict[str, Any]:
        record = self.processor.normalize_metadata(observation)
        self.records.append(record)
        return record

    def query(
        self,
        target_name: str | None = None,
        instrument_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            record
            for record in self.records
            if _matches(record, target_name, instrument_name, start_date, end_date)
        ]


def _matches(
    record: dict[str, Any],
    target_name: str | None,
    instrument_name: str | None,
    start_date: str | None,
    end_date: str | None,
) -> bool:
    if target_name and record.get("target_name") != target_name:
        return False
    if instrument_name and record.get("instrument_name") != instrument_name:
        return False
    observed = _parse_datetime(record.get("date_obs"))
    if start_date and observed and observed < _parse_datetime(start_date):
        return False
    if end_date and observed and observed > _parse_datetime(end_date):
        return False
    return True


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
