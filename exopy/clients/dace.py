from __future__ import annotations

from pathlib import Path
from typing import Any

from exopy.exceptions import DaceClientError


class DaceClient:
    """Thin boundary around ``dace-query``.

    Keeping DACE calls here makes the domain objects easy to test and gives the
    project one place to absorb API changes.
    """

    def get_star_properties(self, target: str) -> dict[str, Any]:
        """Fetch stellar metadata.

        TODO: Wire this to the relevant DACE target/catalog endpoint once the
        exact source of stellar parameters is chosen.
        """
        return {"target_name": target}

    def query_observations(
        self,
        filters: dict[str, Any],
        file_type: str | list[str] | None = None,
        drs_version: str | list[str] | None = None,
        limit: int | None = None,
        output_format: str = "dict",
    ) -> list[dict[str, Any]]:
        """List available spectroscopy products from DACE without downloading."""
        try:
            from dace_query.spectroscopy import Spectroscopy

            result = Spectroscopy.browse_products(
                filters=filters,
                file_type=file_type,
                drs_version=drs_version,
                output_format=output_format,
            )
        except Exception as exc:  # pragma: no cover - depends on remote service
            msg = "Could not browse DACE spectroscopy products."
            raise DaceClientError(msg) from exc

        rows = _rows_from_dace_result(result)
        if limit is None:
            return rows
        return rows[:limit]

    def download_spectroscopy(
        self,
        filters: dict[str, Any],
        file_type: str,
        drs_version: str,
        output_directory: Path,
        refresh: bool = False,
    ) -> Path:
        """Download reduced spectroscopy products from DACE."""
        output_directory.mkdir(parents=True, exist_ok=True)
        try:
            from dace_query.spectroscopy import Spectroscopy

            downloaded = Spectroscopy.download(
                file_type=file_type,
                filters=filters,
                drs_version=drs_version,
                output_directory=str(output_directory),
            )
        except Exception as exc:  # pragma: no cover - depends on remote service
            msg = "Could not download DACE spectroscopy products."
            raise DaceClientError(msg) from exc

        if downloaded is None:
            return output_directory
        return Path(downloaded)


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
