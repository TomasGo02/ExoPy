import numpy as np
import pytest

from exopy.data import Data
from exopy.observation import Observation, ObservationMetadata
from exopy.storage.hdf5 import HDF5Store

h5py = pytest.importorskip("h5py")


def test_hdf5_store_round_trips_observation(tmp_path):
    store = HDF5Store(tmp_path / "observations.h5")
    observation = Observation(
        metadata=ObservationMetadata(
            spectrum_id="obs/1",
            target_name="TOI/178",
            instrument_name="ESPRESSO19",
            drs_version="3.0",
            file_type="s1d",
        ),
        data=Data(arrays={"flux": np.array([1.0, 2.0, 3.0])}),
    )

    store.write_observation(observation)
    loaded = store.read_observations("TOI/178")

    assert len(loaded) == 1
    assert loaded[0].metadata.spectrum_id == "obs/1"
    assert loaded[0].metadata.target_name == "TOI/178"
    assert loaded[0].metadata.instrument_name == "ESPRESSO19"
    assert loaded[0].metadata.drs_version == "3.0"
    np.testing.assert_allclose(loaded[0].require_data().arrays["flux"], [1.0, 2.0, 3.0])


def test_hdf5_store_returns_empty_list_when_file_or_target_is_missing(tmp_path):
    store = HDF5Store(tmp_path / "observations.h5")

    assert store.read_observations("missing") == []

    with h5py.File(store.path, "w"):
        pass

    assert store.read_observations("missing") == []
