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
        refresh: bool = False,
    ) -> list[Observation]:
        """Fetch available observation metadata into memory without downloading data."""
        if self.products and not refresh:
            return self.observations

        filters = self._target_filters()
        try:
            self.products = self.client.search_products(
                filters=filters,
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
        return self.observations

    def available_instruments(
        self,
        product_type: str | None = None,
        version: str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
    ) -> list[str]:
        """Return sorted instrument names from in-memory product metadata."""
        products = self._filter_products(
            self.products,
            product_type=product_type,
            version=version,
            start_date=start_date,
            end_date=end_date,
        )
        return _unique_sorted(products, "instrument_name")

    def available_product_types(
        self,
        instrument: Instrument | str | None = None,
        version: str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
    ) -> list[str]:
        """Return sorted product types from in-memory product metadata."""
        products = self._filter_products(
            self.products,
            instrument=instrument,
            version=version,
            start_date=start_date,
            end_date=end_date,
        )
        values: set[str] = set()
        for product in products:
            for key in ("file_ext", "file_type"):
                value = product.get(key)
                if value:
                    values.add(str(value))
        return sorted(values)

    def observation_date_range(
        self,
        instrument: Instrument | str | None = None,
        product_type: str | None = None,
        version: str | None = None,
    ) -> tuple[datetime | None, datetime | None]:
        """Return earliest/latest dates from in-memory product metadata."""
        products = self._filter_products(
            self.products,
            instrument=instrument,
            product_type=product_type,
            version=version,
        )
        dates = [
            date
            for product in products
            if (date := _product_datetime(product)) is not None
        ]
        if not dates:
            return None, None
        return min(dates), max(dates)

    def observation_count(
        self,
        instrument: Instrument | str | None = None,
        product_type: str | None = None,
        version: str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
    ) -> int:
        """Return the number of in-memory product metadata rows."""
        return len(
            self._filter_products(
                self.products,
                instrument=instrument,
                product_type=product_type,
                version=version,
                start_date=start_date,
                end_date=end_date,
            )
        )

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
        return self.download_observations(
            instrument=instrument,
            product_type=product_type,
            refresh=refresh,
        )

    def download_observations(
        self,
        instrument: Instrument | str | None = None,
        product_type: str | None = None,
        version: str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        file_rootnames: list[str] | tuple[str, ...] | None = None,
        refresh: bool = False,
    ) -> list[Observation]:
        """Return matching observations, loading cached data before downloading misses."""
        self._require_metadata()
        products = self._filter_products(
            self.products,
            instrument=instrument,
            product_type=product_type,
            version=version,
            start_date=start_date,
            end_date=end_date,
            file_rootnames=file_rootnames,
        )
        if not products:
            self.observations = []
            return []

        cached = [] if refresh else self._cached_observations_for(products)
        missing_products = _missing_products(products, cached)
        imported: list[Observation] = []
        if missing_products:
            imported = self._download_products(
                products=missing_products,
                product_type=product_type,
                version=version
                or (instrument.drs_version if isinstance(instrument, Instrument) else None),
                refresh=refresh,
                prefer_file_rootname=file_rootnames is not None,
            )

        self.observations = _order_observations(products, [*cached, *imported])
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

    def _target_filters(self) -> dict[str, Any]:
        return {"target_name": {"equals": [self.name, *self.aliases]}}

    def _filter_products(
        self,
        products: list[dict[str, Any]],
        instrument: Instrument | str | None = None,
        product_type: str | None = None,
        version: str | None = None,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        file_rootnames: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        return [
            product
            for product in products
            if _product_matches(
                product,
                instrument=instrument,
                product_type=product_type,
                version=version,
                start_date=start_date,
                end_date=end_date,
                file_rootnames=file_rootnames,
            )
        ]

    def _require_metadata(self) -> None:
        if not self.products:
            msg = "Call search_observations() before downloading observations."
            raise ValueError(msg)

    def _cached_observations_for(self, products: list[dict[str, Any]]) -> list[Observation]:
        cached = self.cache.load_observations(self.name)
        return [
            observation
            for observation in cached
            if any(_same_product(product, observation) for product in products)
        ]

    def _download_products(
        self,
        products: list[dict[str, Any]],
        product_type: str | None,
        version: str | None,
        refresh: bool,
        prefer_file_rootname: bool = False,
    ) -> list[Observation]:
        resolved_product_type = _resolve_product_type(product_type, products)
        resolved_version = _resolve_version(version)
        filters = _download_filters(products, prefer_file_rootname=prefer_file_rootname)
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
        imported = self.cache.import_products(
            download_path,
            target_name=self.name,
            products=products,
        )
        self.audit_logger.record(
            "conversion",
            target=self.name,
            observations=len(imported),
        )
        return imported


def _product_matches(
    product: dict[str, Any],
    instrument: Instrument | str | None = None,
    product_type: str | None = None,
    version: str | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
    file_rootnames: list[str] | tuple[str, ...] | None = None,
) -> bool:
    if instrument is not None and _product_instrument(product) != _instrument_name(instrument):
        return False
    if product_type is not None and _product_type(product) != product_type:
        return False
    if version is not None and _product_version(product) != version:
        return False
    if file_rootnames is not None and _product_file_rootname(product) not in set(file_rootnames):
        return False
    observed = _product_datetime(product)
    if start_date is not None and observed is not None and observed < _coerce_datetime(start_date):
        return False
    if end_date is not None and observed is not None and observed > _coerce_datetime(end_date):
        return False
    return True


def _instrument_name(instrument: Instrument | str) -> str:
    if isinstance(instrument, Instrument):
        return instrument.dace_name
    return instrument


def _product_instrument(product: dict[str, Any]) -> str | None:
    value = product.get("instrument_name")
    return str(value) if value else None


def _product_type(product: dict[str, Any]) -> str | None:
    value = product.get("file_ext") or product.get("file_type")
    return str(value) if value else None


def _product_version(product: dict[str, Any]) -> str | None:
    if product.get("drs_version"):
        return str(product["drs_version"])
    parts = [
        product.get("version_major"),
        product.get("version_minor"),
        product.get("version_patch"),
    ]
    if all(part is not None for part in parts):
        return ".".join(str(part) for part in parts)
    if product.get("drs_id"):
        return str(product["drs_id"])
    return None


def _product_file_rootname(product: dict[str, Any]) -> str | None:
    value = product.get("file_rootname") or product.get("product")
    return str(value) if value else None


def _same_product(product: dict[str, Any], observation: Observation) -> bool:
    product_keys = _product_keys(product)
    observation_keys = _observation_product_keys(observation)
    return bool(product_keys & observation_keys)


def _product_keys(product: dict[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for name in ("spectrum_id", "product_id", "file_rootname", "product"):
        value = product.get(name)
        if value:
            keys.add((_normalized_key_name(name), str(value)))
    return keys


def _observation_product_keys(observation: Observation) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    metadata = observation.metadata
    if metadata.spectrum_id:
        keys.add(("spectrum_id", str(metadata.spectrum_id)))
    for name in ("product_id", "file_rootname", "product"):
        value = metadata.headers.get(name)
        if value:
            keys.add((_normalized_key_name(name), str(value)))
    return keys


def _normalized_key_name(name: str) -> str:
    if name == "product":
        return "file_rootname"
    return name


def _missing_products(
    products: list[dict[str, Any]],
    cached: list[Observation],
) -> list[dict[str, Any]]:
    return [
        product
        for product in products
        if not any(_same_product(product, observation) for observation in cached)
    ]


def _order_observations(
    products: list[dict[str, Any]],
    observations: list[Observation],
) -> list[Observation]:
    ordered: list[Observation] = []
    for product in products:
        for observation in observations:
            if _same_product(product, observation) and observation not in ordered:
                ordered.append(observation)
                break
    return ordered


def _unique_sorted(rows: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({str(row[key]) for row in rows if row.get(key)})


def _download_filters(
    products: list[dict[str, Any]],
    prefer_file_rootname: bool = False,
) -> dict[str, dict[str, list[Any]]]:
    if prefer_file_rootname:
        file_rootnames = [
            _product_file_rootname(product)
            for product in products
            if _product_file_rootname(product)
        ]
        if file_rootnames:
            return {"file_rootname": {"equals": file_rootnames}}

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


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = _parse_datetime(value)
    if parsed is None:
        msg = f"Could not parse datetime value: {value}"
        raise ValueError(msg)
    return parsed
