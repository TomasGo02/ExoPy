import pytest

from exopy.core.instrument import Instrument


@pytest.mark.parametrize(
    "instrument, expected",
    [
        (Instrument(name="ESPRESSO", version="19"), "ESPRESSO19"),
        (Instrument(name="ESPRESSO19", version="19"), "ESPRESSO19"),
        (Instrument(name="HARPS"), "HARPS"),
    ],
)
def test_dace_name(instrument, expected):
    assert instrument.dace_name == expected


def test_group_is_unversioned_name():
    instrument = Instrument(name="ESPRESSO", version="19")

    assert instrument.group == "ESPRESSO"


def test_as_filters_includes_instrument_name():
    instrument = Instrument(name="ESPRESSO", version="19")

    assert instrument.as_filters() == {
        "instrument_name": {"equals": ["ESPRESSO19"]},
    }


def test_as_filters_includes_mode_when_present():
    instrument = Instrument(name="ESPRESSO", version="19", mode="HR")

    assert instrument.as_filters() == {
        "instrument_name": {"equals": ["ESPRESSO19"]},
        "instrument_mode": {"equals": ["HR"]},
    }
