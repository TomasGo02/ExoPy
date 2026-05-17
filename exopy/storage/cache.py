from __future__ import annotations

from dataclasses import replace
import tarfile
from pathlib import Path
from typing import Any

from exopy.core.observation import Observation
from exopy.ports.interfaces import StorageBackend
from exopy.pipeline.processing import ObservationProcessor
from exopy.storage.hdf5 import HDF5Store


class Cache:
    """Manage downloaded products and normalized local storage."""

    def __init__(self, root: Path, store: StorageBackend | None = None) -> None:
        self.root = root
        self.downloads_dir = root / "downloads"
        self.products_dir = root / "products"
        self.store = store or HDF5Store(root / "observations.h5")
        self.processor = ObservationProcessor()
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.products_dir.mkdir(parents=True, exist_ok=True)

    def import_products(
        self,
        path: Path,
        target_name: str,
        products: list[dict[str, Any]] | None = None,
    ) -> list[Observation]:
        """Import a FITS file or archive into HDF5 and return observations."""
        fits_paths = self._materialize_products(path)
        observations = []
        for path in fits_paths:
            observation = Observation.from_fits(path, target_name=target_name)
            observation = _with_product_metadata(observation, products or [])
            self.processor.quality_control(observation)
            observations.append(self.processor.convert(observation))
        for observation in observations:
            self.store.save_observation(observation)
        return observations

    def load_observations(self, target_name: str) -> list[Observation]:
        """Load imported observations for a target."""
        return self.store.load_observations(target_name)

    def _materialize_products(self, path: Path) -> list[Path]:
        path = Path(path)
        if path.is_dir():
            return sorted(path.rglob("*.fits"))
        if path.suffix == ".fits":
            return [path]
        if path.suffix in {".tar", ".gz", ".tgz"}:
            with tarfile.open(path) as archive:
                self._safe_extract(archive)
            return sorted(self.products_dir.rglob("*.fits"))
        return []

    def index_observations(
        self,
        target_name: str | None = None,
        instrument_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, object]]:
        """Return indexed metadata from the configured storage backend."""
        return self.store.index_observations(
            target_name=target_name,
            instrument_name=instrument_name,
            start_date=start_date,
            end_date=end_date,
        )

    def _safe_extract(self, archive: tarfile.TarFile) -> None:
        for member in archive.getmembers():
            destination = (self.products_dir / member.name).resolve()
            if not destination.is_relative_to(self.products_dir.resolve()):
                msg = f"archive member escapes products directory: {member.name}"
                raise ValueError(msg)
        archive.extractall(self.products_dir)


def _with_product_metadata(
    observation: Observation,
    products: list[dict[str, Any]],
) -> Observation:
    if not products:
        return observation

    product = _matching_product(observation, products)
    if product is None:
        return observation

    headers = {**product, **observation.metadata.headers}
    metadata = replace(
        observation.metadata,
        spectrum_id=observation.metadata.spectrum_id or product.get("spectrum_id"),
        instrument_name=observation.metadata.instrument_name
        if observation.metadata.instrument_name != "unknown"
        else str(product.get("instrument_name", "unknown")),
        version=observation.metadata.version or _version_from_product(product),
        product_type=observation.metadata.product_type
        or product.get("file_ext")
        or product.get("file_type"),
        headers=headers,
    )
    return Observation(metadata=metadata, data=observation.data)


def _matching_product(
    observation: Observation,
    products: list[dict[str, Any]],
) -> dict[str, Any] | None:
    spectrum_id = observation.metadata.spectrum_id
    if spectrum_id is not None:
        for product in products:
            if str(product.get("spectrum_id")) == str(spectrum_id):
                return product

    source_name = observation.metadata.source_path.name if observation.metadata.source_path else ""
    for product in products:
        file_rootname = str(product.get("file_rootname") or product.get("product") or "")
        if file_rootname and Path(file_rootname).name == source_name:
            return product

    if len(products) == 1:
        return products[0]
    return None


def _version_from_product(product: dict[str, Any]) -> str | None:
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
