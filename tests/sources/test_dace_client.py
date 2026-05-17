import sys
import types

import pytest

from exopy.sources.dace import DaceClient
from exopy.core.exceptions import DaceClientError
from exopy.ports.interfaces import DataSourceConnector


class FakeSpectroscopy:
    query_calls = []
    download_calls = []

    @classmethod
    def browse_products(cls, **kwargs):
        cls.query_calls.append(kwargs)
        return {
            "spectrum_id": [1, 2, 3],
            "product": ["a.fits", "b.fits", "c.fits"],
        }

    @classmethod
    def download(cls, **kwargs):
        cls.download_calls.append(kwargs)
        return "/tmp/products.tar"

    @classmethod
    def query_database(cls, **kwargs):
        raise AssertionError("query_database should not be called")


@pytest.fixture
def fake_dace_query(monkeypatch):
    FakeSpectroscopy.query_calls = []
    FakeSpectroscopy.download_calls = []

    dace_query = types.ModuleType("dace_query")
    spectroscopy = types.ModuleType("dace_query.spectroscopy")
    spectroscopy.Spectroscopy = FakeSpectroscopy
    monkeypatch.setitem(sys.modules, "dace_query", dace_query)
    monkeypatch.setitem(sys.modules, "dace_query.spectroscopy", spectroscopy)

    return FakeSpectroscopy


def test_search_products_uses_dace_browse_products(fake_dace_query):
    client = DaceClient()

    rows = client.search_products(
        filters={"target_name": {"equals": ["TOI178"]}},
        product_type="s1d",
        version="latest",
        limit=2,
    )

    assert rows == [
        {"spectrum_id": 1, "product": "a.fits"},
        {"spectrum_id": 2, "product": "b.fits"},
    ]
    assert fake_dace_query.query_calls == [
        {
            "filters": {"target_name": {"equals": ["TOI178"]}},
            "file_type": "s1d",
            "drs_version": "latest",
            "output_format": "dict",
        }
    ]


def test_dace_client_is_a_data_source_connector():
    assert isinstance(DaceClient(), DataSourceConnector)


def test_search_products_wraps_dace_errors(monkeypatch, fake_dace_query):
    def fail(**kwargs):
        raise RuntimeError("network failed")

    monkeypatch.setattr(fake_dace_query, "browse_products", fail)

    with pytest.raises(DaceClientError, match="browse DACE spectroscopy products"):
        DaceClient().search_products(filters={"target_name": {"equals": ["TOI178"]}})
