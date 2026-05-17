from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Protocol, runtime_checkable

if TYPE_CHECKING:
    from exopy.core.observation import Observation


@runtime_checkable
class DataSourceConnector(Protocol):
    """Generic boundary for astronomical product catalogs and archives."""

    def get_target_properties(self, target: str) -> dict[str, Any]:
        """Return normalized metadata for an astronomical target or alias."""

    def search_products(
        self,
        filters: Mapping[str, Any],
        product_type: str | list[str] | None = None,
        version: str | list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return product metadata rows without downloading payload data."""

    def download_products(
        self,
        filters: Mapping[str, Any],
        product_type: str,
        version: str,
        output_directory: Path,
        refresh: bool = False,
    ) -> Path:
        """Download matching products and return the local file or directory."""


@runtime_checkable
class StorageBackend(Protocol):
    """Persistence boundary for normalized observations and indexes."""

    def save_observation(self, observation: Observation) -> None:
        """Persist one normalized observation."""

    def load_observations(self, target_name: str) -> list[Observation]:
        """Load normalized observations for a target."""

    def index_observations(
        self,
        target_name: str | None = None,
        instrument_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return indexed metadata records filtered by common dimensions."""
