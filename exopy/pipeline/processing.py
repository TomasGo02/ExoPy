from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from exopy.core.data import Data
from exopy.core.observation import Observation


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Basic quality-control summary for one observation."""

    passed: bool
    invalid_counts: dict[str, int]
    total_rows: int


class ObservationProcessor:
    """Normalize metadata, run simple QC, and prepare efficient arrays."""

    def normalize_metadata(self, observation: Observation) -> dict[str, Any]:
        metadata = observation.metadata
        return {
            "spectrum_id": str(metadata.spectrum_id or ""),
            "target_name": metadata.target_name.strip(),
            "instrument_name": metadata.instrument_name.strip(),
            "version": metadata.version or "",
            "product_type": metadata.product_type or "",
            "date_obs": metadata.headers.get("DATE-OBS")
            or metadata.headers.get("date_obs")
            or metadata.headers.get("date"),
            "source_path": str(metadata.source_path or ""),
        }

    def quality_control(self, observation: Observation) -> QualityReport:
        data = observation.require_data()
        invalid_counts: dict[str, int] = {}
        total_rows = 0
        for name, values in data.arrays.items():
            array = np.asarray(values)
            if total_rows == 0 and array.ndim > 0:
                total_rows = len(array)
            if np.issubdtype(array.dtype, np.number):
                invalid_counts[name] = int((~np.isfinite(array)).sum())
        return QualityReport(
            passed=all(count == 0 for count in invalid_counts.values()),
            invalid_counts=invalid_counts,
            total_rows=total_rows,
        )

    def convert(self, observation: Observation) -> Observation:
        """Return an observation with contiguous numeric arrays for storage."""
        data = observation.require_data()
        converted = Data(
            arrays={
                name: np.ascontiguousarray(values)
                for name, values in data.arrays.items()
            },
            metadata=dict(data.metadata),
        )
        return Observation(metadata=observation.metadata, data=converted)
