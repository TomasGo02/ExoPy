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
    data_type: str | None = None
    source_path: Path | None = None
    snr: float | None = None
    berv: float | None = None
    airmass: float | None = None
    exposition_time: float | None = None
    headers: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.data_type is None and self.product_type is not None:
            object.__setattr__(self, "data_type", self.product_type)


@dataclass(slots=True)
class Observation:
    """One observation plus lazy access to its reduced data arrays."""

    metadata: ObservationMetadata
    data: Data | None = None

    @classmethod
    def from_product(cls, product: dict[str, Any], target_name: str) -> "Observation":
        """Create a metadata-only observation from a DACE product row."""
        data_type = product.get("file_ext") or product.get("file_type")
        metadata = ObservationMetadata(
            spectrum_id=product.get("spectrum_id"),
            target_name=target_name,
            instrument_name=str(product.get("instrument_name", "unknown")),
            version=_version_from_product(product),
            product_type=data_type,
            data_type=data_type,
            snr=_metadata_float(product, _SNR_KEYS),
            berv=_metadata_float(product, _BERV_KEYS),
            airmass=_metadata_float(product, _AIRMASS_KEYS),
            exposition_time=_metadata_float(product, _EXPOSITION_TIME_KEYS),
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
            headers = _headers_from_hdul(hdul)
            arrays = _arrays_from_hdul(hdul)

        data_type = _metadata_value(primary_header, _DATA_TYPE_KEYS)
        metadata = ObservationMetadata(
            spectrum_id=primary_header.get("SPECTRUM")
            or primary_header.get("SPECT_ID"),
            target_name=target_name or primary_header.get("OBJECT", "unknown"),
            instrument_name=primary_header.get("INSTRUME", "unknown"),
            version=primary_header.get("DRS_VER"),
            product_type=data_type,
            data_type=data_type,
            source_path=path,
            snr=_metadata_float(headers, _SNR_KEYS),
            berv=_metadata_float(headers, _BERV_KEYS),
            airmass=_metadata_float(headers, _AIRMASS_KEYS),
            exposition_time=_metadata_float(headers, _EXPOSITION_TIME_KEYS),
            headers=headers,
        )
        return cls(
            metadata=metadata,
            data=Data(arrays=arrays, metadata=primary_header, data_type=data_type),
        )

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


def _headers_from_hdul(hdul: fits.HDUList) -> dict[str, Any]:
    primary_header = dict(hdul[0].header)
    headers: dict[str, Any] = {**primary_header, "hdus": {}}
    hdu_headers = headers["hdus"]
    seen: dict[str, int] = {}
    for index, hdu in enumerate(hdul):
        name = _unique_hdu_header_name(_hdu_header_name(hdu, index), seen)
        hdu_headers[name] = dict(hdu.header)
    return headers


def _hdu_header_name(hdu: Any, index: int) -> str:
    if index == 0:
        return "PRIMARY"
    return hdu.name or f"HDU_{index}"


def _unique_hdu_header_name(name: str, seen: dict[str, int]) -> str:
    count = seen.get(name, 0)
    seen[name] = count + 1
    if count == 0:
        return name
    return f"{name}_{count + 1}"


_SNR_KEYS = (
    "HIERARCH ESO QC ORDER50 SNR",
    "ESO QC ORDER50 SNR",
    "HIERARCH ESO QC SNR50",
    "ESO QC SNR50",
    "HIERARCH ESO QC SNR",
    "ESO QC SNR",
    "SNR",
    "SNR50",
    "SNR_50",
    "snr",
)
_BERV_KEYS = (
    "HIERARCH ESO QC BERV",
    "ESO QC BERV",
    "HIERARCH ESO DRS BERV",
    "ESO DRS BERV",
    "BERV",
    "berv",
)
_AIRMASS_KEYS = (
    "HIERARCH ESO OBS AIRM",
    "ESO OBS AIRM",
    "HIERARCH ESO TEL AIRM START",
    "ESO TEL AIRM START",
    "HIERARCH ESO TEL AIRMASS",
    "ESO TEL AIRMASS",
    "AIRMASS",
    "airmass",
)
_EXPOSITION_TIME_KEYS = (
    "HIERARCH ESO OCS EM EXPTIME",
    "ESO OCS EM EXPTIME",
    "HIERARCH ESO DET EXP TIME",
    "ESO DET EXP TIME",
    "EXPTIME",
    "EXPOSURE",
    "exptime",
    "exposure_time",
    "exposition_time",
)
_DATA_TYPE_KEYS = (
    "HIERARCH ESO PRO CATG",
    "ESO PRO CATG",
    "PRO CATG",
    "DATA TYPE",
    "DATA_TYPE",
    "DATATYPE",
)


def _metadata_float(headers: dict[str, Any], candidates: tuple[str, ...]) -> float | None:
    value = _metadata_value(headers, candidates)
    return _as_float(value)


def _metadata_value(headers: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    normalized_candidates = [_normalized_header_key(candidate) for candidate in candidates]
    for header in _iter_header_mappings(headers):
        normalized_header = {
            _normalized_header_key(str(key)): value
            for key, value in header.items()
        }
        for candidate in normalized_candidates:
            if candidate in normalized_header:
                return normalized_header[candidate]
    return None


def _iter_header_mappings(headers: dict[str, Any]):
    yield headers
    hdus = headers.get("hdus")
    if isinstance(hdus, dict):
        yield from (header for header in hdus.values() if isinstance(header, dict))


def _normalized_header_key(value: str) -> str:
    return value.removeprefix("HIERARCH ").replace("-", " ").replace("_", " ").upper()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
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
