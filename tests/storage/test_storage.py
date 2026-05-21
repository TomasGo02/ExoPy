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
            snr=42.0,
            berv=-12.5,
            airmass=1.23,
            exposition_time=900.0,
            headers={
                "DATE-OBS": "2020-01-02T03:04:05",
                "hdus": {
                    "PRIMARY": {"OBJECT": "TOI178"},
                    "FLUX": {"BUNIT": "electron"},
                },
            },
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
    assert loaded[0].metadata.data_type == "s1d"
    assert loaded[0].metadata.snr == 42.0
    assert loaded[0].metadata.berv == -12.5
    assert loaded[0].metadata.airmass == 1.23
    assert loaded[0].metadata.exposition_time == 900.0
    assert loaded[0].metadata.headers["DATE-OBS"] == "2020-01-02T03:04:05"
    assert loaded[0].metadata.headers["data_type"] == "s1d"
    assert loaded[0].metadata.headers["hdus"]["PRIMARY"]["OBJECT"] == "TOI178"
    assert loaded[0].metadata.headers["hdus"]["FLUX"]["BUNIT"] == "electron"
    assert loaded[0].require_data().data_type == "s1d"
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
            "2020-01-02T03:04:05/file_types/S1D_A/observations/obs-1/arrays/flux"
        )
        assert path in h5


def test_hdf5_store_separates_matching_observations_by_file_type(tmp_path):
    store = HDF5Store(tmp_path / "observations.h5")
    base_metadata = {
        "spectrum_id": "obs-1",
        "target_name": "TOI178",
        "instrument_name": "ESPRESSO19",
        "headers": {"DATE-OBS": "2020-01-02T03:04:05"},
    }
    s1d = Observation(
        metadata=ObservationMetadata(**base_metadata, product_type="S1D_A"),
        data=Data(arrays={"flux": np.array([1.0])}),
    )
    s2d = Observation(
        metadata=ObservationMetadata(**base_metadata, product_type="S2D_A"),
        data=Data(arrays={"flux": np.array([2.0])}),
    )

    store.save_observation(s1d)
    store.save_observation(s2d)

    loaded = sorted(
        store.load_observations("TOI178"),
        key=lambda observation: observation.metadata.product_type or "",
    )

    assert [observation.metadata.product_type for observation in loaded] == [
        "S1D_A",
        "S2D_A",
    ]
    assert [observation.metadata.data_type for observation in loaded] == [
        "S1D_A",
        "S2D_A",
    ]
    assert [observation.require_data().data_type for observation in loaded] == [
        "S1D_A",
        "S2D_A",
    ]
    np.testing.assert_allclose(loaded[0].require_data().arrays["flux"], [1.0])
    np.testing.assert_allclose(loaded[1].require_data().arrays["flux"], [2.0])


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
            "data_type": "",
            "product_id": "",
            "file_rootname": "",
            "date_obs": "2020-01-02T03:04:05",
            "source_path": "",
            "snr": "",
            "berv": "",
            "airmass": "",
            "exposition_time": "",
        }
    ]
    assert store.index_observations(start_date="2021-01-01") == []

    with h5py.File(store.path, "w"):
        pass

    assert store.load_observations("missing") == []
