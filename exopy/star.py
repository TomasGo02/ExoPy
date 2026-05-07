from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from exopy.clients.dace import DaceClient
from exopy.instrument import Instrument
from exopy.observation import Observation
from exopy.storage.cache import Cache


@dataclass(slots=True)
class Star:
    """High-level object users create to work with one stellar target."""

    name: str
    cache_dir: Path | str = ".exopy"
    client: DaceClient = field(default_factory=DaceClient)
    cache: Cache = field(init=False)
    properties: dict[str, Any] | None = field(default=None, init=False)
    products: list[dict[str, Any]] = field(default_factory=list, init=False)
    observations: list[Observation] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.cache = Cache(Path(self.cache_dir))

    def fetch_properties(self, refresh: bool = False) -> dict[str, Any]:
        """Fetch and cache stellar properties from DACE."""
        if self.properties is None or refresh:
            self.properties = self.client.get_star_properties(self.name)
        return self.properties

    def query_observations(
        self,
        instrument: Instrument | None = None,
        file_type: str | list[str] | None = None,
        drs_version: str | list[str] | None = None,
        limit: int | None = None,
        download: bool = False,
        refresh: bool = False,
    ) -> list[Observation]:
        """Query available DACE products, store them, and optionally download them."""
        filters = self._filters(instrument)
        self.products = self.client.query_observations(
            filters=filters,
            file_type=file_type,
            drs_version=drs_version or (instrument.drs_version if instrument else None),
            limit=limit,
        )
        self.observations = [
            Observation.from_product(product, target_name=self.name)
            for product in self.products
        ]
        if download:
            self._download_products(
                file_type=file_type,
                drs_version=drs_version or (instrument.drs_version if instrument else "latest"),
                refresh=refresh,
            )
        return self.observations

    def available_instruments(self) -> list[str]:
        """Return sorted instrument names from the latest product query."""
        return _unique_sorted(self.products, "instrument_name")

    def available_file_types(self) -> list[str]:
        """Return sorted file/product types from the latest product query."""
        values: set[str] = set()
        for product in self.products:
            for key in ("file_ext", "file_type"):
                value = product.get(key)
                if value:
                    values.add(str(value))
        return sorted(values)

    def observation_date_range(self) -> tuple[datetime | None, datetime | None]:
        """Return the earliest and latest observation datetimes in queried products."""
        dates = [
            date
            for product in self.products
            if (date := _product_datetime(product)) is not None
        ]
        if not dates:
            return None, None
        return min(dates), max(dates)

    def products_dataframe(self):
        """Return queried products as a pandas DataFrame."""
        import pandas as pd

        return pd.DataFrame(self.products)

    def fetch_observations(
        self,
        instrument: Instrument | None = None,
        file_type: str = "s1d",
        refresh: bool = False,
    ) -> list[Observation]:
        """Download products, import them into HDF5, and return observations."""
        self.query_observations(
            instrument=instrument,
            file_type=file_type,
            drs_version=instrument.drs_version if instrument else None,
            download=True,
            refresh=refresh,
        )
        return self.observations

    def load_cached_observations(self) -> list[Observation]:
        """Load observations that have already been imported into local storage."""
        self.observations = self.cache.load_observations(self.name)
        return self.observations

    def _filters(self, instrument: Instrument | None = None) -> dict[str, Any]:
        filters: dict[str, Any] = {
            "target_name": {"equals": [self.name]},
        }
        if instrument:
            filters.update(instrument.as_filters())
        return filters

    def _download_products(
        self,
        file_type: str | list[str] | None,
        drs_version: str | list[str] | None,
        refresh: bool,
    ) -> None:
        if not self.products:
            self.observations = []
            return

        resolved_file_type = _resolve_file_type(file_type, self.products)
        resolved_drs_version = _resolve_drs_version(drs_version)
        filters = _download_filters(self.products)
        download_path = self.client.download_spectroscopy(
            filters=filters,
            file_type=resolved_file_type,
            drs_version=resolved_drs_version,
            output_directory=self.cache.downloads_dir,
            refresh=refresh,
        )
        self.observations = self.cache.import_products(
            download_path,
            target_name=self.name,
        )


def _unique_sorted(rows: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({str(row[key]) for row in rows if row.get(key)})


def _download_filters(products: list[dict[str, Any]]) -> dict[str, dict[str, list[Any]]]:
    spectrum_ids = [product["spectrum_id"] for product in products if product.get("spectrum_id")]
    if spectrum_ids:
        return {"spectrum_id": {"equals": spectrum_ids}}
    product_ids = [product["product_id"] for product in products if product.get("product_id")]
    if product_ids:
        return {"product_id": {"equals": product_ids}}
    msg = "Cannot download queried products because DACE did not return spectrum_id or product_id."
    raise ValueError(msg)


def _resolve_file_type(
    file_type: str | list[str] | None,
    products: list[dict[str, Any]],
) -> str:
    if isinstance(file_type, str):
        return file_type
    if isinstance(file_type, list) and len(file_type) == 1:
        return file_type[0]
    values = {
        str(value)
        for product in products
        for key in ("file_ext", "file_type")
        if (value := product.get(key))
    }
    if len(values) == 1:
        return next(iter(values))
    msg = "Pass a single file_type when downloading observations."
    raise ValueError(msg)


def _resolve_drs_version(drs_version: str | list[str] | None) -> str:
    if drs_version is None:
        return "latest"
    if isinstance(drs_version, str):
        return drs_version
    if len(drs_version) == 1:
        return drs_version[0]
    msg = "Pass a single drs_version when downloading observations."
    raise ValueError(msg)


def _product_datetime(product: dict[str, Any]) -> datetime | None:
    for key in ("date_obs", "date", "obs_date", "mjd"):
        value = product.get(key)
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            parsed = _parse_datetime(value)
            if parsed:
                return parsed

    file_rootname = product.get("file_rootname") or product.get("product")
    if not file_rootname:
        return None

    match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", str(file_rootname))
    if match:
        return _parse_datetime(match.group(0))

    match = re.search(r"\d{4}-\d{2}-\d{2}", str(file_rootname))
    if match:
        return _parse_datetime(match.group(0))

    return None


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
