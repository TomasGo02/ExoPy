from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
from pathlib import Path
from typing import Any

from exopy.audit import AuditLogger
from exopy.ports.interfaces import DataSourceConnector
from exopy.core.observation import Observation
from exopy.storage.cache import Cache


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    """Declarative, serializable query description."""

    target: str
    aliases: tuple[str, ...] = ()
    instrument_name: str | None = None
    instrument_mode: str | None = None
    start_date: str | date | datetime | None = None
    end_date: str | date | datetime | None = None
    product_type: str | list[str] | None = None
    version: str | list[str] | None = None
    limit: int | None = None
    extra_filters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "AcquisitionConfig":
        """Build a config from a plain dictionary."""
        aliases = values.get("aliases", ())
        return cls(
            target=values["target"],
            aliases=tuple(aliases),
            instrument_name=values.get("instrument_name"),
            instrument_mode=values.get("instrument_mode"),
            start_date=values.get("start_date"),
            end_date=values.get("end_date"),
            product_type=values.get("product_type"),
            version=values.get("version"),
            limit=values.get("limit"),
            extra_filters=dict(values.get("extra_filters", {})),
        )

    def to_filters(self) -> dict[str, Any]:
        """Convert the config to the common archive filter shape."""
        filters = dict(self.extra_filters)
        targets = [self.target, *self.aliases]
        filters["target_name"] = {"equals": targets}
        if self.instrument_name:
            filters["instrument_name"] = {"equals": [self.instrument_name]}
        if self.instrument_mode:
            filters["instrument_mode"] = {"equals": [self.instrument_mode]}
        if self.start_date or self.end_date:
            date_filter: dict[str, str] = {}
            if self.start_date:
                date_filter["gte"] = _date_string(self.start_date)
            if self.end_date:
                date_filter["lte"] = _date_string(self.end_date)
            filters["date_obs"] = date_filter
        return filters


class AcquisitionService:
    """Coordinate search, download, integrity checks, and import."""

    def __init__(
        self,
        source: DataSourceConnector,
        cache: Cache,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.source = source
        self.cache = cache
        self.audit_logger = audit_logger or AuditLogger()

    def search(self, config: AcquisitionConfig) -> list[dict[str, Any]]:
        filters = config.to_filters()
        try:
            rows = self.source.search_products(
                filters=filters,
                product_type=config.product_type,
                version=config.version,
                limit=config.limit,
            )
        except Exception as exc:
            self.audit_logger.record("search_error", filters=filters, error=str(exc))
            raise
        self.audit_logger.record("search", filters=filters, rows=len(rows))
        return rows

    def download(
        self,
        products: list[dict[str, Any]],
        config: AcquisitionConfig,
        refresh: bool = False,
    ) -> Path:
        filters = _download_filters(products)
        product_type = _resolve_product_type(config.product_type, products)
        version = _resolve_version(config.version)
        try:
            path = self.source.download_products(
                filters=filters,
                product_type=product_type,
                version=version,
                output_directory=self.cache.downloads_dir,
                refresh=refresh,
            )
            verify_download(path)
        except Exception as exc:
            self.audit_logger.record("download_error", filters=filters, error=str(exc))
            raise
        self.audit_logger.record(
            "download",
            filters=filters,
            product_type=product_type,
            version=version,
            path=path,
            checksum=sha256sum(path) if Path(path).is_file() else None,
        )
        return path

    def run(self, config: AcquisitionConfig, download: bool = False) -> list[Observation]:
        products = self.search(config)
        observations = [
            Observation.from_product(product, target_name=config.target)
            for product in products
        ]
        if not download:
            return observations
        path = self.download(products, config)
        imported = self.cache.import_products(path, target_name=config.target)
        self.audit_logger.record("conversion", path=path, observations=len(imported))
        return imported


def verify_download(path: Path | str) -> None:
    """Check that a download produced a non-empty product artifact."""
    path = Path(path)
    if not path.exists():
        msg = f"downloaded path does not exist: {path}"
        raise FileNotFoundError(msg)
    if path.is_file() and path.stat().st_size == 0:
        msg = f"downloaded file is empty: {path}"
        raise ValueError(msg)
    if path.is_dir() and not any(path.rglob("*")):
        msg = f"downloaded directory is empty: {path}"
        raise ValueError(msg)


def sha256sum(path: Path | str) -> str:
    """Return a SHA-256 digest for a downloaded file."""
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_filters(products: list[dict[str, Any]]) -> dict[str, dict[str, list[Any]]]:
    spectrum_ids = [product["spectrum_id"] for product in products if product.get("spectrum_id")]
    if spectrum_ids:
        return {"spectrum_id": {"equals": spectrum_ids}}
    product_ids = [product["product_id"] for product in products if product.get("product_id")]
    if product_ids:
        return {"product_id": {"equals": product_ids}}
    msg = "Cannot download queried products because no spectrum_id or product_id was returned."
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


def _date_string(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
