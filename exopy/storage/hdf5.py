from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from exopy.core.data import Data
from exopy.ports.interfaces import StorageBackend
from exopy.core.observation import Observation, ObservationMetadata
from exopy.pipeline.processing import ObservationProcessor


class HDF5Store(StorageBackend):
    """Persist observations in an HDF5 hierarchy.

    Layout:
        /targets/{target_name}/instruments/{instrument_name}/dates/{date_obs}
            /file_types/{file_type}/observations/{observation_id}/arrays
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.processor = ObservationProcessor()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save_observation(self, observation: Observation) -> None:
        import h5py

        data = observation.require_data()
        metadata = observation.metadata
        observation_id = str(metadata.spectrum_id or metadata.source_path or "unknown")
        attrs = _hdf5_attrs(metadata)

        with h5py.File(self.path, "a") as h5:
            group = h5.require_group(_observation_path(attrs, observation_id))
            group.attrs.update(attrs)
            arrays = group.require_group("arrays")
            arrays.attrs["data_type"] = data.data_type or metadata.data_type or ""
            for name, values in data.arrays.items():
                if name in arrays:
                    del arrays[name]
                arrays.create_dataset(name, data=np.asarray(values), compression="gzip")

    def load_observations(self, target_name: str) -> list[Observation]:
        import h5py

        if not self.path.exists():
            return []

        observations: list[Observation] = []
        with h5py.File(self.path, "r") as h5:
            root_path = f"targets/{_safe_name(target_name)}"
            root = h5.get(root_path)
            if root is None:
                return []

            for observation_id, group in _iter_observation_groups(root):
                observations.append(_observation_from_group(observation_id, group, target_name))
        return observations

    def index_observations(
        self,
        target_name: str | None = None,
        instrument_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return stored observation metadata filtered by common dimensions."""
        import h5py

        if not self.path.exists():
            return []

        records: list[dict[str, Any]] = []
        with h5py.File(self.path, "r") as h5:
            targets = h5.get("targets")
            if targets is None:
                return []
            for _, target_group in targets.items():
                for observation_id, group in _iter_observation_groups(target_group):
                    record = _record_from_group(observation_id, group)
                    if _record_matches(record, target_name, instrument_name, start_date, end_date):
                        records.append(record)
        return records


def _safe_name(value: Any) -> str:
    return str(value).replace("/", "_")


def _observation_path(attrs: dict[str, str], observation_id: str) -> str:
    return (
        f"targets/{_safe_name(attrs['target_name'])}"
        f"/instruments/{_safe_name(attrs['instrument_name'] or 'unknown')}"
        f"/dates/{_safe_name(attrs['date_obs'] or 'unknown')}"
        f"/file_types/{_safe_name(attrs['product_type'] or 'unknown')}"
        f"/observations/{_safe_name(observation_id)}"
    )


def _iter_observation_groups(root: Any):
    instruments = root.get("instruments")
    if instruments is not None:
        for _, instrument_group in instruments.items():
            dates = instrument_group.get("dates")
            if dates is None:
                continue
            for _, date_group in dates.items():
                file_types = date_group.get("file_types")
                if file_types is not None:
                    for _, file_type_group in file_types.items():
                        observations = file_type_group.get("observations")
                        if observations is not None:
                            yield from observations.items()

                observations = date_group.get("observations")
                if observations is not None:
                    yield from observations.items()
        return

    observations = root.get("observations")
    if observations is not None:
        yield from observations.items()


def _observation_from_group(
    observation_id: str,
    group: Any,
    fallback_target_name: str,
) -> Observation:
    arrays = {name: dataset[()] for name, dataset in group["arrays"].items()}
    source_path = group.attrs.get("source_path", "")
    metadata = ObservationMetadata(
        spectrum_id=group.attrs.get("spectrum_id", observation_id),
        target_name=group.attrs.get("target_name", fallback_target_name),
        instrument_name=group.attrs.get("instrument_name", "unknown"),
        version=group.attrs.get("version"),
        product_type=group.attrs.get("product_type"),
        data_type=group.attrs.get("data_type"),
        source_path=Path(source_path) if source_path else None,
        snr=_optional_float(group.attrs.get("snr")),
        berv=_optional_float(group.attrs.get("berv")),
        airmass=_optional_float(group.attrs.get("airmass")),
        exposition_time=_optional_float(group.attrs.get("exposition_time")),
        headers=_headers_from_group_attrs(group.attrs),
    )
    return Observation(
        metadata=metadata,
        data=Data(
            arrays=arrays,
            data_type=group["arrays"].attrs.get("data_type") or metadata.data_type,
        ),
    )


def _record_from_group(observation_id: str, group: Any) -> dict[str, Any]:
    return {
        "spectrum_id": group.attrs.get("spectrum_id", observation_id),
        "target_name": group.attrs.get("target_name", ""),
        "instrument_name": group.attrs.get("instrument_name", ""),
        "version": group.attrs.get("version", ""),
        "product_type": group.attrs.get("product_type", ""),
        "data_type": group.attrs.get("data_type", ""),
        "product_id": group.attrs.get("product_id", ""),
        "file_rootname": group.attrs.get("file_rootname", ""),
        "date_obs": group.attrs.get("date_obs", ""),
        "source_path": group.attrs.get("source_path", ""),
        "snr": group.attrs.get("snr", ""),
        "berv": group.attrs.get("berv", ""),
        "airmass": group.attrs.get("airmass", ""),
        "exposition_time": group.attrs.get("exposition_time", ""),
    }


def _hdf5_attrs(metadata: ObservationMetadata) -> dict[str, str]:
    return {
        "spectrum_id": str(metadata.spectrum_id or ""),
        "target_name": metadata.target_name,
        "instrument_name": metadata.instrument_name,
        "version": metadata.version or "",
        "product_type": metadata.product_type or "",
        "data_type": metadata.data_type or metadata.product_type or "",
        "product_id": str(metadata.headers.get("product_id") or ""),
        "file_rootname": str(metadata.headers.get("file_rootname") or ""),
        "source_path": str(metadata.source_path or ""),
        "snr": _hdf5_optional_float(metadata.snr),
        "berv": _hdf5_optional_float(metadata.berv),
        "airmass": _hdf5_optional_float(metadata.airmass),
        "exposition_time": _hdf5_optional_float(metadata.exposition_time),
        "headers_json": json.dumps(_json_safe(metadata.headers)),
        "date_obs": str(
            metadata.headers.get("DATE-OBS")
            or metadata.headers.get("date_obs")
            or metadata.headers.get("date")
            or _date_from_file_rootname(metadata.headers.get("file_rootname"))
            or ""
        ),
    }


def _hdf5_optional_float(value: float | None) -> str:
    if value is None:
        return ""
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _headers_from_group_attrs(attrs: Any) -> dict[str, Any]:
    headers_json = attrs.get("headers_json")
    if headers_json:
        try:
            headers = json.loads(headers_json)
        except json.JSONDecodeError:
            headers = {}
    else:
        headers = {}

    headers.setdefault("product_id", attrs.get("product_id", ""))
    headers.setdefault("file_rootname", attrs.get("file_rootname", ""))
    headers.setdefault("date_obs", attrs.get("date_obs", ""))
    headers.setdefault("data_type", attrs.get("data_type", ""))
    return headers


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _date_from_file_rootname(value: Any) -> str | None:
    if not value:
        return None
    import re

    match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", str(value))
    if match:
        return match.group(0)

    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    if match:
        return match.group(0)
    return None


def _record_matches(
    record: dict[str, Any],
    target_name: str | None,
    instrument_name: str | None,
    start_date: str | None,
    end_date: str | None,
) -> bool:
    if target_name and record.get("target_name") != target_name:
        return False
    if instrument_name and record.get("instrument_name") != instrument_name:
        return False
    if start_date and record.get("date_obs") and str(record["date_obs"]) < start_date:
        return False
    if end_date and record.get("date_obs") and str(record["date_obs"]) > end_date:
        return False
    return True
