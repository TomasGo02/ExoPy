from __future__ import annotations

import tarfile
from pathlib import Path

from exopy.observation import Observation
from exopy.storage.hdf5 import HDF5Store


class Cache:
    """Manage downloaded products and normalized local storage."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.downloads_dir = root / "downloads"
        self.products_dir = root / "products"
        self.store = HDF5Store(root / "observations.h5")
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.products_dir.mkdir(parents=True, exist_ok=True)

    def import_products(self, path: Path, target_name: str) -> list[Observation]:
        """Import a FITS file or archive into HDF5 and return observations."""
        fits_paths = self._materialize_products(path)
        observations = [
            Observation.from_fits(path, target_name=target_name) for path in fits_paths
        ]
        for observation in observations:
            self.store.write_observation(observation)
        return observations

    def load_observations(self, target_name: str) -> list[Observation]:
        """Load imported observations for a target."""
        return self.store.read_observations(target_name)

    def _materialize_products(self, path: Path) -> list[Path]:
        path = Path(path)
        if path.is_dir():
            return sorted(path.rglob("*.fits"))
        if path.suffix == ".fits":
            return [path]
        if path.suffix in {".tar", ".gz", ".tgz"}:
            with tarfile.open(path) as archive:
                archive.extractall(self.products_dir)
            return sorted(self.products_dir.rglob("*.fits"))
        return []
