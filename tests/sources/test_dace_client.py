import sys
import types

import pytest

from exopy.sources.dace import DaceClient
from exopy.core.exceptions import DaceClientError
from exopy.ports.interfaces import DataSourceConnector


class FakeSpectroscopy:
    query_calls = []
    download_calls = []
    instances = []

    def __init__(self, dace_instance=None):
        self.dace_instance = dace_instance
        self.instances.append(self)

    def browse_products(self, **kwargs):
        self.query_calls.append(kwargs)
        return {
            "spectrum_id": [1, 2, 3],
            "product": ["a.fits", "b.fits", "c.fits"],
        }

    def download(self, **kwargs):
        self.download_calls.append(kwargs)
        return "/tmp/products.tar"

    def query_database(self, **kwargs):
        raise AssertionError("query_database should not be called")


class FakeDaceClass:
    instances = []

    def __init__(self, dace_rc_config_path=None):
        self.dace_rc_config_path = dace_rc_config_path
        self.instances.append(self)


@pytest.fixture
def fake_dace_query(monkeypatch):
    FakeSpectroscopy.query_calls = []
    FakeSpectroscopy.download_calls = []
    FakeSpectroscopy.instances = []
    FakeDaceClass.instances = []

    dace_query = types.ModuleType("dace_query")
    dace_query.DaceClass = FakeDaceClass
    spectroscopy = types.ModuleType("dace_query.spectroscopy")
    spectroscopy.SpectroscopyClass = FakeSpectroscopy
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
    assert fake_dace_query.instances[0].dace_instance is FakeDaceClass.instances[0]


def test_dace_client_is_a_data_source_connector():
    assert isinstance(DaceClient(), DataSourceConnector)


def test_search_products_wraps_dace_errors(monkeypatch, fake_dace_query):
    def fail(**kwargs):
        raise RuntimeError("network failed")

    monkeypatch.setattr(fake_dace_query, "browse_products", fail)

    with pytest.raises(DaceClientError, match="browse DACE spectroscopy products"):
        DaceClient().search_products(filters={"target_name": {"equals": ["TOI178"]}})


def test_dace_client_passes_dacerc_path_to_dace_class(tmp_path, fake_dace_query):
    dacerc = tmp_path / ".dacerc"
    client = DaceClient(dace_rc_config_path=dacerc)

    client.search_products(filters={"target_name": {"equals": ["TOI178"]}})

    assert FakeDaceClass.instances[0].dace_rc_config_path == dacerc


def test_dace_client_reads_dacerc_path_from_exopy_config(tmp_path, monkeypatch, fake_dace_query):
    dacerc = tmp_path / "private.dacerc"
    (tmp_path / "exopy_config.toml").write_text(
        f'[dace]\ndace_rc_config_path = "{dacerc}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = DaceClient()

    client.search_products(filters={"target_name": {"equals": ["TOI178"]}})

    assert FakeDaceClass.instances[0].dace_rc_config_path == dacerc
