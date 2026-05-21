from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

ArrayLike = np.ndarray


@dataclass(slots=True)
class Data:
    """Wrapper around observation arrays with transformation helpers.

    This class represents the data wrapper described in the project interface.
    """

    arrays: dict[str, ArrayLike]
    metadata: dict[str, Any] = field(default_factory=dict)
    data_type: str | None = None

    def copy(self) -> "Data":
        """Return a deep-ish copy of the arrays and metadata dictionary."""
        return Data(
            arrays={
                name: np.array(values, copy=True)
                for name, values in self.arrays.items()
            },
            metadata=dict(self.metadata),
            data_type=self.data_type,
        )

    def select(self, *columns: str) -> "Data":
        """Return a new wrapper containing only selected arrays."""
        return Data(
            arrays={column: self.arrays[column] for column in columns},
            metadata=dict(self.metadata),
            data_type=self.data_type,
        )

    def apply(self, column: str, transform: Callable[[ArrayLike], ArrayLike]) -> "Data":
        """Apply a transformation to a single array and return a new wrapper."""
        next_data = self.copy()
        next_data.arrays[column] = transform(next_data.arrays[column])
        return next_data

    def normalize(self, column: str) -> "Data":
        """Normalize an array by subtracting its mean and dividing by its std."""

        def _normalize(values: ArrayLike) -> ArrayLike:
            std = np.nanstd(values)
            if std == 0:
                return values - np.nanmean(values)
            return (values - np.nanmean(values)) / std

        return self.apply(column, _normalize)

    def mask_invalid(self, *columns: str) -> "Data":
        """Drop rows where any selected column contains NaN or infinite values."""
        if not columns:
            columns = tuple(self.arrays)

        mask = np.ones(len(next(iter(self.arrays.values()))), dtype=bool)
        for column in columns:
            mask &= np.isfinite(self.arrays[column])

        return Data(
            arrays={name: values[mask] for name, values in self.arrays.items()},
            metadata=dict(self.metadata),
            data_type=self.data_type,
        )

    def to_pandas(self):
        """Convert one-dimensional arrays to a pandas DataFrame."""
        import pandas as pd

        return pd.DataFrame(self.arrays)
