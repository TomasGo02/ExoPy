from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

from exopy.core.data import Data


@dataclass(frozen=True, slots=True)
class ObservationMetadata:
    """Metadata that identifies and describes one reduced observation."""

    spectrum_id: int | str | None
    target_name: str
    instrument_name: str
    version: str | None = None
    product_type: str | None = None
    source_path: Path | None = None
    headers: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Observation:
    """One observation plus lazy access to its reduced data arrays."""

    metadata: ObservationMetadata
    data: Data | None = None

    @classmethod
    def from_product(cls, product: dict[str, Any], target_name: str) -> "Observation":
        """Create a metadata-only observation from a DACE product row."""
        metadata = ObservationMetadata(
            spectrum_id=product.get("spectrum_id"),
            target_name=target_name,
            instrument_name=str(product.get("instrument_name", "unknown")),
            version=_version_from_product(product),
            product_type=product.get("file_ext") or product.get("file_type"),
            headers=dict(product),
        )
        return cls(metadata=metadata)

    @classmethod
    def from_fits(
        cls, path: str | Path, target_name: str | None = None
    ) -> "Observation":
        """Create an observation by reading a local FITS file."""
        path = Path(path)
        with fits.open(path, memmap=False) as hdul:
            primary_header = dict(hdul[0].header)
            arrays = _arrays_from_hdul(hdul)

        metadata = ObservationMetadata(
            spectrum_id=primary_header.get("SPECTRUM")
            or primary_header.get("SPECT_ID"),
            target_name=target_name or primary_header.get("OBJECT", "unknown"),
            instrument_name=primary_header.get("INSTRUME", "unknown"),
            version=primary_header.get("DRS_VER"),
            product_type=primary_header.get("HIERARCH ESO PRO CATG"),
            source_path=path,
            headers=primary_header,
        )
        return cls(metadata=metadata, data=Data(arrays=arrays, metadata=primary_header))

    @property
    def target_name(self) -> str:
        return self.metadata.target_name

    @property
    def instrument_name(self) -> str:
        return self.metadata.instrument_name

    def require_data(self) -> Data:
        """Return data or raise a clear error if this is only a metadata shell."""
        if self.data is None:
            msg = "Observation data has not been loaded yet."
            raise ValueError(msg)
        return self.data


def _arrays_from_hdul(hdul: fits.HDUList) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    for index, hdu in enumerate(hdul):
        if hdu.data is None:
            continue
        name = hdu.name.lower() if hdu.name else f"hdu_{index}"
        arrays[name] = np.asarray(hdu.data)
    return arrays


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
