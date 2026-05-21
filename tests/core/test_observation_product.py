from exopy.core.observation import Observation


def test_observation_from_product_wraps_dace_metadata():
    observation = Observation.from_product(
        {
            "spectrum_id": "75079",
            "instrument_name": "ESPRESSO19",
            "file_ext": "S1D_A",
            "version_major": 3,
            "version_minor": 3,
            "version_patch": 10,
            "snr": 120.5,
            "berv": -4.2,
            "airmass": 1.1,
            "exposition_time": 600.0,
        },
        target_name="TOI178",
    )

    assert observation.metadata.spectrum_id == "75079"
    assert observation.metadata.target_name == "TOI178"
    assert observation.metadata.instrument_name == "ESPRESSO19"
    assert observation.metadata.product_type == "S1D_A"
    assert observation.metadata.data_type == "S1D_A"
    assert observation.metadata.version == "3.3.10"
    assert observation.metadata.snr == 120.5
    assert observation.metadata.berv == -4.2
    assert observation.metadata.airmass == 1.1
    assert observation.metadata.exposition_time == 600.0
    assert observation.data is None
