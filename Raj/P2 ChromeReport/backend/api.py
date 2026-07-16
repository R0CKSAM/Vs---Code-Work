from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse

from .processor import FrequencyDatasetProcessor
from .utils import (
    DIMENSION_COLUMNS,
    FILTER_COLUMNS,
    available_week_columns,
    build_week_label_map,
    distinct_values,
    load_json_param,
    scan_week_files,
)


@dataclass
class QueryContext:
    page: int
    page_size: int
    filters: dict[str, list[str]]
    group_by: list[str]
    sort_model: list[dict[str, Any]]
    search: str


class DatasetService:
    def __init__(self, data_dir: Path, parquet_path: Path) -> None:
        self.processor = FrequencyDatasetProcessor(data_dir, parquet_path)
        self._df: pd.DataFrame | None = None
        self._metadata_cache: dict[str, Any] | None = None

    def refresh(self, force: bool = False) -> pd.DataFrame:
        self.processor.process_if_needed(force=force)
        self._df = pd.read_parquet(self.processor.output_path)
        self._metadata_cache = None
        return self._df

    def dataframe(self) -> pd.DataFrame:
        if self._df is None:
            return self.refresh()
        return self._df

    def metadata(self) -> dict[str, Any]:
        if self._metadata_cache is not None:
            return self._metadata_cache

        df = self.dataframe()
        source_files = scan_week_files(self.processor.data_dir)
        week_label_map = build_week_label_map(source_files)

        self._metadata_cache = {
            "weeks": available_week_columns(df),
            "week_labels": week_label_map,
            "markets": distinct_values(df, "Market"),
            "msos": distinct_values(df, "MSO"),
            "cities": distinct_values(df, "City"),
            "head_ends": distinct_values(df, "Head End"),
            "channel_names": distinct_values(df, "Channel Name"),
            "cr_numbers": distinct_values(df, "CR No"),
            "mso_types": distinct_values(df, "MSO Type"),
            "transmissions": distinct_values(df, "Transmission"),
            "bands": distinct_values(df, "Band"),
            "tv_channel_numbers": distinct_values(df, "TV Channel No"),
            "status_options": ["Changed", "Unchanged"],
            "source_files": [path.name for path in source_files],
            "totals": {
                "weeks": len(available_week_columns(df)),
                "channels": int(df["Channel Name"].nunique()) if "Channel Name" in df.columns else 0,
                "markets": int(df["Market"].nunique()) if "Market" in df.columns else 0,
                "records": len(df.index),
            },
        }
        return self._metadata_cache

    def query(self, context: QueryContext) -> dict[str, Any]:
        df = self._apply_filters(self.dataframe(), context.filters, context.search)
        week_columns = available_week_columns(df)
        df = self._apply_sorting(df, context.sort_model)

        total_rows = len(df.index)
        start = max((context.page - 1) * context.page_size, 0)
        end = start + context.page_size
        page_df = df.iloc[start:end].copy()

        return {
            "rows": page_df.fillna("").to_dict(orient="records"),
            "total_rows": total_rows,
            "page": context.page,
            "page_size": context.page_size,
            "week_columns": week_columns,
            "summary": self._summary(df),
        }

    def export(self, context: QueryContext, kind: str) -> StreamingResponse:
        df = self._apply_filters(self.dataframe(), context.filters, context.search)
        df = self._apply_sorting(df, context.sort_model)

        buffer = io.BytesIO()
        media_type = "text/csv"
        filename = "frequency_export.csv"

        if kind == "excel":
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Frequency Comparison")
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = "frequency_export.xlsx"
        else:
            buffer.write(df.to_csv(index=False).encode("utf-8"))

        buffer.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(buffer, media_type=media_type, headers=headers)

    def _apply_filters(self, df: pd.DataFrame, filters: dict[str, list[str]], search: str) -> pd.DataFrame:
        filtered = df
        for column, selected_values in filters.items():
            if not selected_values:
                continue

            if column == "Changed State":
                normalized = {str(value).strip().lower() for value in selected_values}
                include_changed = "changed" in normalized
                include_unchanged = "unchanged" in normalized
                if include_changed and not include_unchanged:
                    filtered = filtered[filtered["Total Changes"] > 0]
                elif include_unchanged and not include_changed:
                    filtered = filtered[filtered["Total Changes"] == 0]
                continue

            if column not in filtered.columns:
                continue

            filtered = filtered[filtered[column].astype(str).isin([str(item) for item in selected_values])]

        if search:
            lower_search = search.lower()
            search_columns = [column for column in filtered.columns if column != "Business Key"]
            mask = filtered[search_columns].astype(str).apply(
                lambda row: row.str.lower().str.contains(lower_search, regex=False).any(),
                axis=1,
            )
            filtered = filtered[mask]

        return filtered

    def _apply_sorting(self, df: pd.DataFrame, sort_model: list[dict[str, Any]]) -> pd.DataFrame:
        if not sort_model:
            return df

        columns = [item["colId"] for item in sort_model if item.get("colId") in df.columns]
        ascending = [item.get("sort", "asc") != "desc" for item in sort_model if item.get("colId") in df.columns]
        if not columns:
            return df
        return df.sort_values(by=columns, ascending=ascending, na_position="last")

    @staticmethod
    def _summary(df: pd.DataFrame) -> dict[str, Any]:
        return {
            "visible_rows": len(df.index),
            "visible_markets": int(df["Market"].nunique()) if "Market" in df.columns else 0,
            "visible_channels": int(df["Channel Name"].nunique()) if "Channel Name" in df.columns else 0,
            "visible_weeks": len(available_week_columns(df)),
        }


router = APIRouter()
_service: DatasetService | None = None


def init_service(service: DatasetService) -> None:
    global _service
    _service = service


def get_service() -> DatasetService:
    assert _service is not None
    return _service


def build_context(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    filters: str | None = Query(default=None),
    group_by: str | None = Query(default=None),
    sort_model: str | None = Query(default=None),
    search: str | None = Query(default=""),
) -> QueryContext:
    filter_map = load_json_param(filters, {})
    normalized_filters = {
        key: value if isinstance(value, list) else [value]
        for key, value in filter_map.items()
        if key in FILTER_COLUMNS + ["Changed State"]
    }
    return QueryContext(
        page=page,
        page_size=page_size,
        filters=normalized_filters,
        group_by=load_json_param(group_by, []),
        sort_model=load_json_param(sort_model, []),
        search=(search or "").strip(),
    )


@router.get("/metadata")
def metadata(service: DatasetService = Depends(get_service)) -> JSONResponse:
    return JSONResponse(service.metadata())


@router.get("/data")
def data(
    context: QueryContext = Depends(build_context),
    service: DatasetService = Depends(get_service),
) -> JSONResponse:
    return JSONResponse(service.query(context))


@router.get("/export/csv")
def export_csv(
    context: QueryContext = Depends(build_context),
    service: DatasetService = Depends(get_service),
) -> StreamingResponse:
    return service.export(context, "csv")


@router.get("/export/excel")
def export_excel(
    context: QueryContext = Depends(build_context),
    service: DatasetService = Depends(get_service),
) -> StreamingResponse:
    return service.export(context, "excel")


@router.post("/refresh")
def refresh(service: DatasetService = Depends(get_service)) -> JSONResponse:
    df = service.refresh(force=True)
    return JSONResponse(
        {
            "message": "Dataset refreshed",
            "rows": len(df.index),
            "weeks": available_week_columns(df),
        }
    )
