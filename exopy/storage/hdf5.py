from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from exopy.data import Data
from exopy.observation import Observation, ObservationMetadata


class HDF5Store:
    """Persist observations in an HDF5 hierarchy.

    Layout:
        /targets/{target_name}/observations/{observation_id}/arrays/{array_name}
        /targets/{target_name}/observations/{observation_id}.attrs
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write_observation(self, observation: Observation) -> None:
        import h5py

        data = observation.require_data()
        metadata = observation.metadata
        observation_id = str(metadata.spectrum_id or metadata.source_path or "unknown")

        with h5py.File(self.path, "a") as h5:
            group = h5.require_group(
                f"targets/{_safe_name(metadata.target_name)}/observations/{_safe_name(observation_id)}"
            )
            group.attrs.update(_hdf5_attrs(metadata))
            arrays = group.require_group("arrays")
            for name, values in data.arrays.items():
                if name in arrays:
                    del arrays[name]
                arrays.create_dataset(name, data=np.asarray(values), compression="gzip")

    def read_observations(self, target_name: str) -> list[Observation]:
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
                    drs_version=group.attrs.get("drs_version"),
                    file_type=group.attrs.get("file_type"),
                    headers={},
                )
                observations.append(
                    Observation(metadata=metadata, data=Data(arrays=arrays))
                )
        return observations


def _safe_name(value: Any) -> str:
    return str(value).replace("/", "_")


def _hdf5_attrs(metadata: ObservationMetadata) -> dict[str, str]:
    return {
        "spectrum_id": str(metadata.spectrum_id or ""),
        "target_name": metadata.target_name,
        "instrument_name": metadata.instrument_name,
        "drs_version": metadata.drs_version or "",
        "file_type": metadata.file_type or "",
        "source_path": str(metadata.source_path or ""),
    }
