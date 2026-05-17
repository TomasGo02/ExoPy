from __future__ import annotations

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
        /targets/{target_name}/observations/{observation_id}/arrays/{array_name}
        /targets/{target_name}/observations/{observation_id}.attrs
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

        with h5py.File(self.path, "a") as h5:
            target_group = _safe_name(metadata.target_name)
            observation_group = _safe_name(observation_id)
            group = h5.require_group(f"targets/{target_group}/observations/{observation_group}")
            group.attrs.update(_hdf5_attrs(metadata))
            arrays = group.require_group("arrays")
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
            root_path = f"targets/{_safe_name(target_name)}/observations"
            if root_path not in h5:
                return []

            for observation_id, group in h5[root_path].items():
                arrays = {
                    name: dataset[()] for name, dataset in group["arrays"].items()
                }
                metadata = ObservationMetadata(
                    spectrum_id=group.attrs.get("spectrum_id", observation_id),
                    target_name=group.attrs.get("target_name", target_name),
                    instrument_name=group.attrs.get("instrument_name", "unknown"),
                    version=group.attrs.get("version"),
                    product_type=group.attrs.get("product_type"),
                    headers={
                        "product_id": group.attrs.get("product_id", ""),
                        "file_rootname": group.attrs.get("file_rootname", ""),
                        "date_obs": group.attrs.get("date_obs", ""),
                    },
                )
                observations.append(
                    Observation(metadata=metadata, data=Data(arrays=arrays))
                )
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
                observations = target_group.get("observations")
                if observations is None:
                    continue
                for observation_id, group in observations.items():
                    record = {
                        "spectrum_id": group.attrs.get("spectrum_id", observation_id),
                        "target_name": group.attrs.get("target_name", ""),
                        "instrument_name": group.attrs.get("instrument_name", ""),
                        "version": group.attrs.get("version", ""),
                        "product_type": group.attrs.get("product_type", ""),
                        "product_id": group.attrs.get("product_id", ""),
                        "file_rootname": group.attrs.get("file_rootname", ""),
                        "date_obs": group.attrs.get("date_obs", ""),
                        "source_path": group.attrs.get("source_path", ""),
                    }
                    if _record_matches(record, target_name, instrument_name, start_date, end_date):
                        records.append(record)
        return records


def _safe_name(value: Any) -> str:
    return str(value).replace("/", "_")


def _hdf5_attrs(metadata: ObservationMetadata) -> dict[str, str]:
    return {
        "spectrum_id": str(metadata.spectrum_id or ""),
        "target_name": metadata.target_name,
        "instrument_name": metadata.instrument_name,
        "version": metadata.version or "",
        "product_type": metadata.product_type or "",
        "product_id": str(metadata.headers.get("product_id") or ""),
        "file_rootname": str(metadata.headers.get("file_rootname") or ""),
        "source_path": str(metadata.source_path or ""),
        "date_obs": str(
            metadata.headers.get("DATE-OBS")
            or metadata.headers.get("date_obs")
            or metadata.headers.get("date")
            or _date_from_file_rootname(metadata.headers.get("file_rootname"))
            or ""
        ),
    }


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
