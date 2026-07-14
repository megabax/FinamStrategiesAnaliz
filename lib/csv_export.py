"""Единый формат CSV для отчётов: разделитель «;», десятичная запятая."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

CSV_DELIMITER = ';'
CSV_ENCODING = 'utf-8-sig'


def format_decimal(value: Any, precision: int | None = 6) -> Any:
    """Форматирует число для CSV: десятичный разделитель — запятая."""
    if value is None or value == '':
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if pd.isna(value):
            return ''
        text = f'{value:.{precision}f}' if precision is not None else str(value)
        return text.replace('.', ',')
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == '':
            return value
        try:
            number = float(stripped.replace(',', '.'))
        except ValueError:
            return value
        return format_decimal(number, precision)
    return value


def format_csv_record(
    record: dict[str, Any],
    float_fields: Iterable[str] | None = None,
    float_precision: int = 6,
) -> dict[str, Any]:
    if not float_fields:
        return record
    formatted = dict(record)
    for field in float_fields:
        if field in formatted:
            formatted[field] = format_decimal(formatted[field], float_precision)
    return formatted


def open_csv_writer(path: Path | str, fieldnames: list[str]) -> tuple[Any, csv.DictWriter]:
    file_obj = Path(path).open('w', encoding=CSV_ENCODING, newline='')
    writer = csv.DictWriter(file_obj, fieldnames=fieldnames, delimiter=CSV_DELIMITER)
    return file_obj, writer


def write_dataframe_csv(df: pd.DataFrame, path: Path | str) -> None:
    export_df = df.copy()
    for column in export_df.columns:
        if pd.api.types.is_float_dtype(export_df[column]):
            export_df[column] = export_df[column].map(
                lambda value: format_decimal(value) if pd.notna(value) else '',
            )
    export_df.to_csv(
        path,
        index=False,
        encoding=CSV_ENCODING,
        sep=CSV_DELIMITER,
    )
