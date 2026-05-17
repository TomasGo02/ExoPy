from __future__ import annotations

import tarfile
from pathlib import Path

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

    def import_products(self, path: Path, target_name: str) -> list[Observation]:
        """Import a FITS file or archive into HDF5 and return observations."""
        fits_paths = self._materialize_products(path)
        observations = []
        for path in fits_paths:
            observation = Observation.from_fits(path, target_name=target_name)
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
