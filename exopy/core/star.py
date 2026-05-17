from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from exopy.audit import AuditLogger
from exopy.sources.dace import DaceClient
from exopy.ports.interfaces import DataSourceConnector, StorageBackend
from exopy.core.instrument import Instrument
from exopy.core.observation import Observation
from exopy.storage.cache import Cache


@dataclass(slots=True)
class Star:
    """High-level object users create to work with one stellar target."""

    name: str
    cache_dir: Path | str = ".exopy"
    client: DataSourceConnector = field(default_factory=DaceClient)
    aliases: tuple[str, ...] = ()
    storage_backend: StorageBackend | None = None
    audit_logger: AuditLogger = field(default_factory=AuditLogger)
    cache: Cache = field(init=False)
    properties: dict[str, Any] | None = field(default=None, init=False)
    products: list[dict[str, Any]] = field(default_factory=list, init=False)
    observations: list[Observation] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.cache = Cache(Path(self.cache_dir), store=self.storage_backend)

    def fetch_properties(self, refresh: bool = False) -> dict[str, Any]:
        """Fetch and cache stellar properties from DACE."""
        if self.properties is None or refresh:
            try:
                self.properties = self.client.get_target_properties(self.name)
            except Exception as exc:
                self.audit_logger.record("properties_error", target=self.name, error=str(exc))
                raise
            self.audit_logger.record("properties", target=self.name)
        return self.properties

    def search_observations(
        self,
        instrument: Instrument | None = None,
        product_type: str | list[str] | None = None,
        version: str | list[str] | None = None,
        limit: int | None = None,
        aliases: list[str] | tuple[str, ...] | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        download: bool = False,
        refresh: bool = False,
    ) -> list[Observation]:
        """Search available products, store metadata, and optionally download them."""
        filters = self._filters(
            instrument,
            aliases=aliases,
            start_date=start_date,
            end_date=end_date,
        )
        try:
            self.products = self.client.search_products(
                filters=filters,
                product_type=product_type,
                version=version or (instrument.drs_version if instrument else None),
                limit=limit,
            )
        except Exception as exc:
            self.audit_logger.record(
                "search_error",
                target=self.name,
                filters=filters,
                error=str(exc),
            )
            raise
        self.audit_logger.record(
            "search",
            target=self.name,
            filters=filters,
            rows=len(self.products),
        )
        self.observations = [
            Observation.from_product(product, target_name=self.name)
            for product in self.products
        ]
        if download:
            self._download_products(
                product_type=product_type,
                version=version or (instrument.drs_version if instrument else "latest"),
                refresh=refresh,
            )
        return self.observations

    def available_instruments(self) -> list[str]:
        """Return sorted instrument names from the latest product query."""
        return _unique_sorted(self.products, "instrument_name")

    def available_product_types(self) -> list[str]:
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
        product_type: str = "s1d",
        refresh: bool = False,
    ) -> list[Observation]:
        """Download products, import them into HDF5, and return observations."""
        self.search_observations(
            instrument=instrument,
            product_type=product_type,
            version=instrument.drs_version if instrument else None,
            download=True,
            refresh=refresh,
        )
        return self.observations

    def load_cached_observations(self) -> list[Observation]:
        """Load observations that have already been imported into local storage."""
        self.observations = self.cache.load_observations(self.name)
        return self.observations

    def index_observations(
        self,
        instrument_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, object]]:
        """Return indexed cached observations for this target."""
        return self.cache.index_observations(
            target_name=self.name,
            instrument_name=instrument_name,
            start_date=start_date,
            end_date=end_date,
        )

    def _filters(
        self,
        instrument: Instrument | None = None,
        aliases: list[str] | tuple[str, ...] | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
    ) -> dict[str, Any]:
        target_names = [self.name, *self.aliases, *(aliases or ())]
        filters: dict[str, Any] = {
            "target_name": {"equals": target_names},
        }
        if instrument:
            filters.update(instrument.as_filters())
        if start_date or end_date:
            date_filter: dict[str, str] = {}
            if start_date:
                date_filter["gte"] = _date_filter_value(start_date)
            if end_date:
                date_filter["lte"] = _date_filter_value(end_date)
            filters["date_obs"] = date_filter
        return filters

    def _download_products(
        self,
        product_type: str | list[str] | None,
        version: str | list[str] | None,
        refresh: bool,
    ) -> None:
        if not self.products:
            self.observations = []
            return

        resolved_product_type = _resolve_product_type(product_type, self.products)
        resolved_version = _resolve_version(version)
        filters = _download_filters(self.products)
        download_path = self.client.download_products(
            filters=filters,
            product_type=resolved_product_type,
            version=resolved_version,
            output_directory=self.cache.downloads_dir,
            refresh=refresh,
        )
        self.audit_logger.record(
            "download",
            target=self.name,
            filters=filters,
            product_type=resolved_product_type,
            version=resolved_version,
            path=download_path,
        )
        self.observations = self.cache.import_products(
            download_path,
            target_name=self.name,
        )
        self.audit_logger.record(
            "conversion",
            target=self.name,
            observations=len(self.observations),
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


def _resolve_product_type(
    product_type: str | list[str] | None,
    products: list[dict[str, Any]],
) -> str:
    if isinstance(product_type, str):
        return product_type
    if isinstance(product_type, list) and len(product_type) == 1:
        return product_type[0]
    values = {
        str(value)
        for product in products
        for key in ("file_ext", "file_type")
        if (value := product.get(key))
    }
    if len(values) == 1:
        return next(iter(values))
    msg = "Pass a single product_type when downloading observations."
    raise ValueError(msg)


def _resolve_version(version: str | list[str] | None) -> str:
    if version is None:
        return "latest"
    if isinstance(version, str):
        return version
    if len(version) == 1:
        return version[0]
    msg = "Pass a single version when downloading observations."
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


def _date_filter_value(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
