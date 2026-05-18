from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from exopy.config import load_config
from exopy.core.exceptions import DaceClientError
from exopy.ports.interfaces import DataSourceConnector


class DaceClient(DataSourceConnector):
    """Thin boundary around ``dace-query``.

    Keeping DACE calls here makes the domain objects easy to test and gives the
    project one place to absorb API changes.
    """

    def __init__(self, dace_rc_config_path: Path | str | None = None) -> None:
        configured_path = load_config().dace_rc_config_path
        self.dace_rc_config_path = (
            Path(dace_rc_config_path)
            if dace_rc_config_path is not None
            else configured_path
        )
        self._spectroscopy = None

    def get_target_properties(self, target: str) -> dict[str, Any]:
        """Fetch stellar metadata.

        TODO: Wire this to the relevant DACE target/catalog endpoint once the
        exact source of stellar parameters is chosen.
        """
        return {"target_name": target}

    def search_products(
        self,
        filters: Mapping[str, Any],
        product_type: str | list[str] | None = None,
        version: str | list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List available products from DACE without downloading."""
        try:
            result = self._spectroscopy_client().browse_products(
                filters=filters,
                file_type=product_type,
                drs_version=version,
                output_format="dict",
            )
        except Exception as exc:  # pragma: no cover - depends on remote service
            msg = "Could not browse DACE spectroscopy products."
            raise DaceClientError(msg) from exc

        rows = _rows_from_dace_result(result)
        if limit is None:
            return rows
        return rows[:limit]

    def download_products(
        self,
        filters: Mapping[str, Any],
        product_type: str,
        version: str,
        output_directory: Path,
        refresh: bool = False,
    ) -> Path:
        """Download matching products from DACE."""
        output_directory.mkdir(parents=True, exist_ok=True)
        try:
            downloaded = self._spectroscopy_client().download(
                file_type=product_type,
                filters=filters,
                drs_version=version,
                output_directory=str(output_directory),
            )
        except Exception as exc:  # pragma: no cover - depends on remote service
            msg = "Could not download DACE spectroscopy products."
            raise DaceClientError(msg) from exc

        if downloaded is None:
            return output_directory
        return Path(downloaded)

    def _spectroscopy_client(self):
        if self._spectroscopy is None:
            from dace_query import DaceClass
            from dace_query.spectroscopy import SpectroscopyClass

            dace = DaceClass(dace_rc_config_path=self.dace_rc_config_path)
            self._spectroscopy = SpectroscopyClass(dace_instance=dace)
        return self._spectroscopy


def _rows_from_dace_result(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    if isinstance(result, list):
        return [dict(row) for row in result]
    if hasattr(result, "to_dict"):
        converted = result.to_dict(orient="records")
        if isinstance(converted, list):
            return converted
    if isinstance(result, dict):
        keys = list(result)
        if not keys:
            return []
        length = len(result[keys[0]])
        return [{key: result[key][index] for key in keys} for index in range(length)]
    return list(result)
