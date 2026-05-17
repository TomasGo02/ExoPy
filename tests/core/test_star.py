from pathlib import Path

from exopy.core.instrument import Instrument
from exopy.core.observation import Observation, ObservationMetadata
from exopy.core.star import Star


class FakeClient:
    def __init__(self):
        self.property_calls = []
        self.query_calls = []
        self.download_calls = []

    def get_target_properties(self, target):
        self.property_calls.append(target)
        return {"target_name": target, "teff": 5700}

    def search_products(
        self,
        filters,
        product_type=None,
        version=None,
        limit=None,
    ):
        self.query_calls.append(
            {
                "filters": filters,
                "product_type": product_type,
                "version": version,
                "limit": limit,
            }
        )
        rows = [
            {
                "spectrum_id": "obs-1",
                "instrument_name": "ESPRESSO19",
                "file_ext": "S1D_A",
                "file_rootname": "2019-12-29/r.ESPRE.2019-12-30T00:37:39.686_S1D_A.fits",
            },
            {
                "spectrum_id": "obs-2",
                "instrument_name": "HARPS",
                "file_ext": "CCF",
                "file_rootname": "2020-01-02/r.HARP.2020-01-03T01:02:03.000_CCF.fits",
            },
        ]
        return rows[:limit]

    def download_products(
        self,
        filters,
        product_type,
        version,
        output_directory,
        refresh=False,
    ):
        self.download_calls.append(
            {
                "filters": filters,
                "product_type": product_type,
                "version": version,
                "output_directory": output_directory,
                "refresh": refresh,
            }
        )
        return Path(output_directory) / "download.tar"


class FakeCache:
    def __init__(self, observations=None):
        self.downloads_dir = Path("/tmp/exopy-downloads")
        self.observations = observations or []
        self.import_calls = []
        self.load_calls = []

    def import_products(self, path, target_name, products=None):
        products = products or []
        self.import_calls.append(
            {"path": path, "target_name": target_name, "products": products}
        )
        self.observations = [
            Observation.from_product(product, target_name=target_name)
            for product in products
        ]
        return self.observations

    def load_observations(self, target_name):
        self.load_calls.append(target_name)
        return self.observations


def test_fetch_properties_caches_result(tmp_path):
    client = FakeClient()
    star = Star("TOI178", cache_dir=tmp_path, client=client)

    assert star.fetch_properties() == {"target_name": "TOI178", "teff": 5700}
    assert star.fetch_properties() == {"target_name": "TOI178", "teff": 5700}

    assert client.property_calls == ["TOI178"]


def test_fetch_properties_refreshes_when_requested(tmp_path):
    client = FakeClient()
    star = Star("TOI178", cache_dir=tmp_path, client=client)

    star.fetch_properties()
    star.fetch_properties(refresh=True)

    assert client.property_calls == ["TOI178", "TOI178"]


def test_search_observations_fetches_only_target_metadata(tmp_path):
    client = FakeClient()
    star = Star("TOI178", cache_dir=tmp_path, client=client, aliases=("TOI-178",))

    observations = star.search_observations()

    assert len(observations) == 2
    assert observations[0].metadata.spectrum_id == "obs-1"
    assert observations[0].metadata.instrument_name == "ESPRESSO19"
    assert observations[0].metadata.product_type == "S1D_A"
    assert observations[0].metadata.headers == {
        "spectrum_id": "obs-1",
        "instrument_name": "ESPRESSO19",
        "file_ext": "S1D_A",
        "file_rootname": "2019-12-29/r.ESPRE.2019-12-30T00:37:39.686_S1D_A.fits",
    }
    assert star.products == [
        {
            "spectrum_id": "obs-1",
            "instrument_name": "ESPRESSO19",
            "file_ext": "S1D_A",
            "file_rootname": "2019-12-29/r.ESPRE.2019-12-30T00:37:39.686_S1D_A.fits",
        },
        {
            "spectrum_id": "obs-2",
            "instrument_name": "HARPS",
            "file_ext": "CCF",
            "file_rootname": "2020-01-02/r.HARP.2020-01-03T01:02:03.000_CCF.fits",
        },
    ]
    assert star.observations == observations
    assert client.query_calls == [
        {
            "filters": {"target_name": {"equals": ["TOI178", "TOI-178"]}},
            "product_type": None,
            "version": None,
            "limit": None,
        }
    ]


def test_search_observations_uses_memory_until_refresh(tmp_path):
    client = FakeClient()
    star = Star("TOI178", cache_dir=tmp_path, client=client)

    star.search_observations()
    star.search_observations()
    star.search_observations(refresh=True)

    assert len(client.query_calls) == 2


def test_product_summary_methods_filter_in_memory_metadata(tmp_path):
    star = Star("TOI178", cache_dir=tmp_path, client=FakeClient())

    star.search_observations()

    start, end = star.observation_date_range()
    assert star.available_instruments() == ["ESPRESSO19", "HARPS"]
    assert star.available_instruments(product_type="S1D_A") == ["ESPRESSO19"]
    assert star.available_product_types() == ["CCF", "S1D_A"]
    assert star.available_product_types(instrument="HARPS") == ["CCF"]
    assert start.isoformat() == "2019-12-30T00:37:39.686000"
    assert end.isoformat() == "2020-01-03T01:02:03"
    assert star.observation_date_range(instrument="HARPS")[0].isoformat() == "2020-01-03T01:02:03"
    assert star.observation_count() == 2
    assert star.observation_count(instrument="ESPRESSO19") == 1
    assert star.observation_count(product_type="CCF") == 1
    assert star.observation_count(start_date="2020-01-01") == 1


def test_products_dataframe_returns_latest_query_results(tmp_path):
    star = Star("TOI178", cache_dir=tmp_path, client=FakeClient())

    star.search_observations()
    frame = star.products_dataframe()

    assert list(frame["spectrum_id"]) == ["obs-1", "obs-2"]


def test_download_observations_requires_metadata_search_first(tmp_path):
    star = Star("TOI178", cache_dir=tmp_path, client=FakeClient())

    try:
        star.download_observations(product_type="S1D_A")
    except ValueError as exc:
        assert "search_observations" in str(exc)
    else:
        raise AssertionError("download_observations should require metadata first")


def test_download_observations_downloads_only_matching_products(tmp_path):
    client = FakeClient()
    star = Star("TOI178", cache_dir=tmp_path, client=client)
    fake_cache = FakeCache()
    star.cache = fake_cache

    star.search_observations()
    observations = star.download_observations(product_type="S1D_A")

    assert [observation.metadata.spectrum_id for observation in observations] == ["obs-1"]
    assert client.download_calls == [
        {
            "filters": {"spectrum_id": {"equals": ["obs-1"]}},
            "product_type": "S1D_A",
            "version": "latest",
            "output_directory": fake_cache.downloads_dir,
            "refresh": False,
        }
    ]
    assert fake_cache.import_calls[0]["products"] == [star.products[0]]
    assert star.observations == fake_cache.observations


def test_download_observations_uses_file_rootname_filter_when_names_are_passed(tmp_path):
    client = FakeClient()
    star = Star("TOI178", cache_dir=tmp_path, client=client)
    fake_cache = FakeCache()
    star.cache = fake_cache

    star.search_observations()
    observations = star.download_observations(
        file_rootnames=["2020-01-02/r.HARP.2020-01-03T01:02:03.000_CCF.fits"],
    )

    assert [observation.metadata.spectrum_id for observation in observations] == ["obs-2"]
    assert client.download_calls == [
        {
            "filters": {
                "file_rootname": {
                    "equals": ["2020-01-02/r.HARP.2020-01-03T01:02:03.000_CCF.fits"]
                }
            },
            "product_type": "CCF",
            "version": "latest",
            "output_directory": fake_cache.downloads_dir,
            "refresh": False,
        }
    ]


def test_download_observations_returns_cached_matches_without_network(tmp_path):
    client = FakeClient()
    cached = Observation(
        metadata=ObservationMetadata(
            spectrum_id="obs-1",
            target_name="TOI178",
            instrument_name="ESPRESSO19",
            product_type="S1D_A",
            headers={
                "file_rootname": "2019-12-29/r.ESPRE.2019-12-30T00:37:39.686_S1D_A.fits"
            },
        )
    )
    star = Star("TOI178", cache_dir=tmp_path, client=client)
    fake_cache = FakeCache(observations=[cached])
    star.cache = fake_cache

    star.search_observations()
    observations = star.download_observations(product_type="S1D_A")

    assert observations == [cached]
    assert client.download_calls == []
    assert fake_cache.import_calls == []


def test_fetch_observations_downloads_and_imports_products(tmp_path):
    client = FakeClient()
    star = Star("TOI178", cache_dir=tmp_path, client=client)
    fake_cache = FakeCache()
    star.cache = fake_cache
    instrument = Instrument(name="ESPRESSO", version="19", drs_version="3.0")

    star.search_observations()
    observations = star.fetch_observations(
        instrument=instrument,
        product_type="S1D_A",
        refresh=True,
    )

    assert [observation.metadata.spectrum_id for observation in observations] == ["obs-1"]
    assert star.observations == fake_cache.observations
    assert client.download_calls[0]["version"] == "3.0"
    assert client.download_calls[0]["product_type"] == "S1D_A"
    assert client.download_calls[0]["filters"] == {
        "spectrum_id": {"equals": ["obs-1"]}
    }
    assert client.download_calls[0]["refresh"] is True


def test_load_cached_observations_updates_star_observations(tmp_path):
    star = Star("TOI178", cache_dir=tmp_path, client=FakeClient())
    fake_cache = FakeCache()
    star.cache = fake_cache

    observations = star.load_cached_observations()

    assert observations == fake_cache.observations
    assert star.observations == fake_cache.observations
    assert fake_cache.load_calls == ["TOI178"]
