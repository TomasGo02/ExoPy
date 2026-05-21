import numpy as np
import pytest

from exopy.core.data import Data


@pytest.fixture
def sample_data():
    return Data(
        arrays={
            "time": np.array([1.0, 2.0, 3.0, 4.0]),
            "rv": np.array([10.0, np.nan, 12.0, np.inf]),
            "flux": np.array([100.0, 101.0, 99.0, 98.0]),
        },
        metadata={"target": "TOI178"},
    )


def test_select_returns_requested_columns_and_preserves_metadata(sample_data):
    sample_data.data_type = "S1D_A"

    selected = sample_data.select("time", "flux")

    assert list(selected.arrays) == ["time", "flux"]
    assert selected.metadata == {"target": "TOI178"}
    assert selected.data_type == "S1D_A"


def test_copy_does_not_share_array_memory(sample_data):
    sample_data.data_type = "S1D_A"

    copied = sample_data.copy()

    copied.arrays["flux"][0] = -1

    assert sample_data.arrays["flux"][0] == 100.0
    assert copied.metadata == sample_data.metadata
    assert copied.metadata is not sample_data.metadata
    assert copied.data_type == "S1D_A"


def test_apply_transforms_one_column_without_mutating_original(sample_data):
    transformed = sample_data.apply("flux", lambda values: values / 100.0)

    np.testing.assert_allclose(transformed.arrays["flux"], [1.0, 1.01, 0.99, 0.98])
    np.testing.assert_allclose(sample_data.arrays["flux"], [100.0, 101.0, 99.0, 98.0])


@pytest.mark.parametrize(
    "values, expected",
    [
        (np.array([1.0, 2.0, 3.0]), np.array([-1.22474487, 0.0, 1.22474487])),
        (np.array([5.0, 5.0, 5.0]), np.array([0.0, 0.0, 0.0])),
    ],
)
def test_normalize_column(values, expected):
    data = Data(arrays={"rv": values})

    normalized = data.normalize("rv")

    np.testing.assert_allclose(normalized.arrays["rv"], expected)


def test_mask_invalid_uses_all_columns_by_default(sample_data):
    sample_data.data_type = "S1D_A"

    masked = sample_data.mask_invalid()

    np.testing.assert_allclose(masked.arrays["time"], [1.0, 3.0])
    np.testing.assert_allclose(masked.arrays["rv"], [10.0, 12.0])
    np.testing.assert_allclose(masked.arrays["flux"], [100.0, 99.0])
    assert masked.data_type == "S1D_A"


def test_mask_invalid_can_use_selected_columns(sample_data):
    masked = sample_data.mask_invalid("time", "flux")

    np.testing.assert_allclose(masked.arrays["time"], [1.0, 2.0, 3.0, 4.0])
    np.testing.assert_allclose(masked.arrays["rv"], [10.0, np.nan, 12.0, np.inf])


def test_to_pandas_returns_dataframe(sample_data):
    frame = sample_data.to_pandas()

    assert list(frame.columns) == ["time", "rv", "flux"]
    assert frame.loc[0, "flux"] == 100.0
