import numpy as np

from exopy.core.data import Data
from exopy.core.observation import Observation, ObservationMetadata
from exopy.pipeline.processing import ObservationProcessor


def test_processor_normalizes_metadata_and_reports_quality():
    observation = Observation(
        metadata=ObservationMetadata(
            spectrum_id="obs-1",
            target_name=" TOI178 ",
            instrument_name=" ESPRESSO19 ",
            headers={"DATE-OBS": "2020-01-02T03:04:05"},
        ),
        data=Data(arrays={"flux": np.array([1.0, np.nan, 3.0])}),
    )
    processor = ObservationProcessor()

    metadata = processor.normalize_metadata(observation)
    report = processor.quality_control(observation)
    converted = processor.convert(observation)

    assert metadata["target_name"] == "TOI178"
    assert metadata["instrument_name"] == "ESPRESSO19"
    assert metadata["date_obs"] == "2020-01-02T03:04:05"
    assert report.passed is False
    assert report.invalid_counts == {"flux": 1}
    assert converted.require_data().arrays["flux"].flags["C_CONTIGUOUS"]
