import numpy as np
import pytest
from astropy.io import fits

from exopy.observation import Observation, ObservationMetadata


def test_from_fits_loads_metadata_and_arrays(tmp_path):
    path = tmp_path / "observation.fits"
    primary = fits.PrimaryHDU()
    primary.header["OBJECT"] = "TOI178"
    primary.header["INSTRUME"] = "ESPRESSO19"
    primary.header["DRS_VER"] = "3.0"
    primary.header["SPECT_ID"] = "obs-1"
    flux = fits.ImageHDU(data=np.array([1.0, 2.0, 3.0]), name="FLUX")
    fits.HDUList([primary, flux]).writeto(path)

    observation = Observation.from_fits(path)

    assert observation.metadata.spectrum_id == "obs-1"
    assert observation.target_name == "TOI178"
    assert observation.instrument_name == "ESPRESSO19"
    assert observation.metadata.drs_version == "3.0"
    assert observation.metadata.source_path == path
    np.testing.assert_allclose(observation.require_data().arrays["flux"], [1.0, 2.0, 3.0])


def test_from_fits_allows_target_override(tmp_path):
    path = tmp_path / "observation.fits"
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(data=np.array([1.0]), name="FLUX")]).writeto(
        path
    )

    observation = Observation.from_fits(path, target_name="Custom Target")

    assert observation.target_name == "Custom Target"


def test_require_data_raises_for_metadata_only_observation():
    observation = Observation(
        metadata=ObservationMetadata(
            spectrum_id="obs-1",
            target_name="TOI178",
            instrument_name="ESPRESSO19",
        )
    )

    with pytest.raises(ValueError, match="has not been loaded"):
        observation.require_data()
