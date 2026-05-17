from pathlib import Path

from exopy.pipeline.acquisition import (
    AcquisitionConfig,
    AcquisitionService,
    sha256sum,
    verify_download,
)
from exopy.storage.cache import Cache


class FakeSource:
    def __init__(self, downloaded_path: Path):
        self.downloaded_path = downloaded_path
        self.query_calls = []
        self.download_calls = []

    def get_target_properties(self, target):
        return {"target_name": target}

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
        return [
            {
                "spectrum_id": "obs-1",
                "instrument_name": "ESPRESSO19",
                "file_ext": "S1D_A",
            }
        ]

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
        return self.downloaded_path


def test_acquisition_config_builds_reproducible_filters():
    config = AcquisitionConfig.from_dict(
        {
            "target": "TOI178",
            "aliases": ["TOI-178", "HD 123"],
            "instrument_name": "ESPRESSO19",
            "instrument_mode": "HR",
            "start_date": "2020-01-01",
            "end_date": "2020-02-01",
            "product_type": "S1D_A",
        }
    )

    assert config.to_filters() == {
        "target_name": {"equals": ["TOI178", "TOI-178", "HD 123"]},
        "instrument_name": {"equals": ["ESPRESSO19"]},
        "instrument_mode": {"equals": ["HR"]},
        "date_obs": {"gte": "2020-01-01", "lte": "2020-02-01"},
    }


def test_acquisition_service_searches_downloads_and_checks_integrity(tmp_path):
    downloaded = tmp_path / "products.tar"
    downloaded.write_text("payload", encoding="utf-8")
    source = FakeSource(downloaded)
    cache = Cache(tmp_path / "cache")
    service = AcquisitionService(source=source, cache=cache)
    config = AcquisitionConfig(target="TOI178", product_type="S1D_A", version="latest")

    products = service.search(config)
    path = service.download(products, config, refresh=True)

    assert path == downloaded
    assert source.query_calls[0]["filters"] == {"target_name": {"equals": ["TOI178"]}}
    assert source.download_calls == [
        {
            "filters": {"spectrum_id": {"equals": ["obs-1"]}},
            "product_type": "S1D_A",
            "version": "latest",
            "output_directory": cache.downloads_dir,
            "refresh": True,
        }
    ]
    assert sha256sum(downloaded)


def test_verify_download_rejects_empty_file(tmp_path):
    empty = tmp_path / "empty.tar"
    empty.touch()

    try:
        verify_download(empty)
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("verify_download should reject empty files")
