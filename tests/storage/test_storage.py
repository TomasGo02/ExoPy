import numpy as np
import pytest

from exopy.core.data import Data
from exopy.ports.interfaces import StorageBackend
from exopy.core.observation import Observation, ObservationMetadata
from exopy.storage.hdf5 import HDF5Store

h5py = pytest.importorskip("h5py")


def test_hdf5_store_is_a_storage_backend(tmp_path):
    assert isinstance(HDF5Store(tmp_path / "observations.h5"), StorageBackend)


def test_hdf5_store_round_trips_observation(tmp_path):
    store = HDF5Store(tmp_path / "observations.h5")
    observation = Observation(
        metadata=ObservationMetadata(
            spectrum_id="obs/1",
            target_name="TOI/178",
            instrument_name="ESPRESSO19",
            version="3.0",
            product_type="s1d",
        ),
        data=Data(arrays={"flux": np.array([1.0, 2.0, 3.0])}),
    )

    store.save_observation(observation)
    loaded = store.load_observations("TOI/178")

    assert len(loaded) == 1
    assert loaded[0].metadata.spectrum_id == "obs/1"
    assert loaded[0].metadata.target_name == "TOI/178"
    assert loaded[0].metadata.instrument_name == "ESPRESSO19"
    assert loaded[0].metadata.version == "3.0"
    np.testing.assert_allclose(loaded[0].require_data().arrays["flux"], [1.0, 2.0, 3.0])


def test_hdf5_store_groups_by_target_instrument_and_datetime(tmp_path):
    store = HDF5Store(tmp_path / "observations.h5")
    observation = Observation(
        metadata=ObservationMetadata(
            spectrum_id="obs-1",
            target_name="TOI178",
            instrument_name="ESPRESSO19",
            product_type="S1D_A",
            headers={"DATE-OBS": "2020-01-02T03:04:05"},
        ),
        data=Data(arrays={"flux": np.array([1.0])}),
    )

    store.save_observation(observation)

    with h5py.File(store.path, "r") as h5:
        path = (
            "targets/TOI178/instruments/ESPRESSO19/dates/"
            "2020-01-02T03:04:05/observations/obs-1/arrays/flux"
        )
        assert path in h5


def test_hdf5_store_returns_empty_list_when_file_or_target_is_missing(tmp_path):
    store = HDF5Store(tmp_path / "observations.h5")

    assert store.load_observations("missing") == []


def test_hdf5_store_indexes_observations_by_target_instrument_and_date(tmp_path):
    store = HDF5Store(tmp_path / "observations.h5")
    observation = Observation(
        metadata=ObservationMetadata(
            spectrum_id="obs-1",
            target_name="TOI178",
            instrument_name="ESPRESSO19",
            headers={"DATE-OBS": "2020-01-02T03:04:05"},
        ),
        data=Data(arrays={"flux": np.array([1.0])}),
    )

    store.save_observation(observation)

    assert store.index_observations(target_name="TOI178", instrument_name="ESPRESSO19") == [
        {
            "spectrum_id": "obs-1",
            "target_name": "TOI178",
            "instrument_name": "ESPRESSO19",
            "version": "",
            "product_type": "",
            "product_id": "",
            "file_rootname": "",
            "date_obs": "2020-01-02T03:04:05",
            "source_path": "",
        }
    ]
    assert store.index_observations(start_date="2021-01-01") == []

    with h5py.File(store.path, "w"):
        pass

    assert store.load_observations("missing") == []
