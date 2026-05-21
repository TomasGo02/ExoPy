import numpy as np
import pytest
from astropy.io import fits

from exopy.core.observation import Observation, ObservationMetadata


def test_from_fits_loads_metadata_and_arrays(tmp_path):
    path = tmp_path / "observation.fits"
    primary = fits.PrimaryHDU()
    primary.header["OBJECT"] = "TOI178"
    primary.header["INSTRUME"] = "ESPRESSO19"
    primary.header["DRS_VER"] = "3.0"
    primary.header["SPECT_ID"] = "obs-1"
    primary.header["HIERARCH ESO PRO CATG"] = "S1D_A"
    primary.header["EXPTIME"] = 1200.0
    primary.header["HIERARCH ESO OBS AIRM"] = 1.23
    primary.header["HIERARCH ESO OCS EM EXPTIME"] = 900.0
    flux = fits.ImageHDU(data=np.array([1.0, 2.0, 3.0]), name="FLUX")
    flux.header["BUNIT"] = "electron"
    flux.header["HIERARCH ESO QC ORDER50 SNR"] = 42.0
    flux.header["HIERARCH ESO QC BERV"] = -12.5
    fits.HDUList([primary, flux]).writeto(path)

    observation = Observation.from_fits(path)

    assert observation.metadata.spectrum_id == "obs-1"
    assert observation.target_name == "TOI178"
    assert observation.instrument_name == "ESPRESSO19"
    assert observation.metadata.version == "3.0"
    assert observation.metadata.product_type == "S1D_A"
    assert observation.metadata.data_type == "S1D_A"
    assert observation.metadata.source_path == path
    assert observation.metadata.snr == 42.0
    assert observation.metadata.berv == -12.5
    assert observation.metadata.airmass == 1.23
    assert observation.metadata.exposition_time == 900.0
    assert observation.metadata.headers["OBJECT"] == "TOI178"
    assert observation.metadata.headers["hdus"]["PRIMARY"]["SPECT_ID"] == "obs-1"
    assert observation.metadata.headers["hdus"]["FLUX"]["BUNIT"] == "electron"
    assert observation.require_data().data_type == "S1D_A"
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


def test_from_fits_prefers_dace_exposition_time_header(tmp_path):
    path = tmp_path / "observation.fits"
    primary = fits.PrimaryHDU()
    primary.header["EXPTIME"] = 1200.0
    primary.header["HIERARCH ESO OCS EM EXPTIME"] = 60.0
    fits.HDUList([primary]).writeto(path)

    observation = Observation.from_fits(path)

    assert observation.metadata.exposition_time == 60.0
