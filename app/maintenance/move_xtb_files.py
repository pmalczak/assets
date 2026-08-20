# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from io import BytesIO
from pathlib import Path
import re
import zipfile

from importers.xtb.read_xtb import inspect_xtb_export_bytes
from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID, DEFAULT_XTB_CLIENT_ID, XTB_FILE_PREFIX
from maintenance.move_downloaded_results import (
    ACTION_MOVED,
    ACTION_SKIPPED,
    KIND_XTB,
    MoveResult,
)

_XTB_ZIP_RE = re.compile(
    r"^(?P<client>\d+)_(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})(?: \(\d+\))?\.zip$"
)


@dataclass(frozen=True)
class XtbZipExport:
    path: Path
    client_id: str
    period_start: date
    period_end: date


@dataclass(frozen=True)
class PreparedXtbExport:
    source: XtbZipExport
    target_name: str
    payload: bytes
    payload_hash: str


def move_xtb_files(
    assets_root: Path,
    download: Path,
    *,
    client_id: str = DEFAULT_XTB_CLIENT_ID,
) -> list[MoveResult]:
    """Rozpakowuje ZIP-y XTB z Downloads do assets/p_xtb, usuwając identyczne duplikaty."""
    exports = _source_exports(download, client_id)
    if not exports:
        return []

    target_dir = assets_root / DEFAULT_XTB_ASSET_ID
    target_dir.mkdir(parents=True, exist_ok=True)

    results: list[MoveResult] = []
    grouped: dict[str, list[PreparedXtbExport]] = {}
    for export in exports:
        prepared = _prepare_export(export)
        grouped.setdefault(prepared.target_name, []).append(prepared)

    for _, group in sorted(grouped.items(), key=lambda item: item[0]):
        results.extend(_move_group(target_dir, group))
    return results


def xtb_target_name(
    client_id: str,
    period_start: date,
    period_end: date,
    data_kind: str = "export",
    suffix: str = ".xlsx",
) -> str:
    return f"{XTB_FILE_PREFIX}_{data_kind}_{client_id}_{period_start.isoformat()}_{period_end.isoformat()}{suffix}"


def _move_group(target_dir: Path, group: list[PreparedXtbExport]) -> list[MoveResult]:
    ordered = sorted(group, key=lambda export: (_iterator(export.source.path.name), export.source.path.name))
    first = ordered[0]
    target = target_dir / first.target_name

    results: list[MoveResult] = []
    if target.is_file():
        target_hash = _sha256_bytes(target.read_bytes())
        for export in ordered:
            if export.payload_hash != target_hash:
                raise ValueError(f"Konflikt treści XTB dla okresu {target.name}: {export.source.path.name}")
            export.source.path.unlink()
            results.append(MoveResult(export.source.path, target, ACTION_SKIPPED, KIND_XTB))
        return results

    incoming_hash = first.payload_hash
    for export in ordered[1:]:
        if export.payload_hash != incoming_hash:
            raise ValueError(f"Konflikt treści XTB dla okresu {target.name}: {export.source.path.name}")

    target.write_bytes(first.payload)
    first.source.path.unlink()
    results.append(MoveResult(first.source.path, target, ACTION_MOVED, KIND_XTB))

    for export in ordered[1:]:
        export.source.path.unlink()
        results.append(MoveResult(export.source.path, target, ACTION_SKIPPED, KIND_XTB))

    return results


def _prepare_export(export: XtbZipExport) -> PreparedXtbExport:
    payload, suffix = _extract_single_export(export.path)
    info = inspect_xtb_export_bytes(payload, suffix)
    data_kind = _data_kind(info)
    target_name = xtb_target_name(
        export.client_id,
        export.period_start,
        export.period_end,
        data_kind=data_kind,
        suffix=suffix,
    )
    return PreparedXtbExport(
        source=export,
        target_name=target_name,
        payload=payload,
        payload_hash=_sha256_bytes(payload),
    )


def _extract_single_export(path: Path) -> tuple[bytes, str]:
    with zipfile.ZipFile(path) as archive:
        export_names = [
            name for name in archive.namelist()
            if Path(name).suffix.lower() in {".xlsx", ".xls", ".csv"}
            and not name.endswith("/")
        ]
        if len(export_names) != 1:
            raise ValueError(f"Expected exactly one XTB export file in {path.name}, got {export_names}")
        export_name = export_names[0]
        return archive.read(export_name), Path(export_name).suffix.lower()


def _data_kind(info) -> str:
    sheet_names = {sheet.sheet_name for sheet in info}
    tokens = []
    if "Open Positions" in sheet_names:
        tokens.append("open")
    if "Closed Positions" in sheet_names:
        tokens.append("closed")
    if "Cash Operations" in sheet_names:
        tokens.append("cash")
    return "_".join(tokens) if tokens else "export"


def _source_exports(download: Path, client_id: str) -> list[XtbZipExport]:
    result = []
    for path in sorted(download.glob(f"{client_id}_*.zip")):
        parsed = parse_xtb_zip_name(path)
        if parsed is not None and parsed.client_id == client_id:
            result.append(parsed)
    return result


def parse_xtb_zip_name(path: Path) -> XtbZipExport | None:
    match = _XTB_ZIP_RE.fullmatch(path.name)
    if not match:
        return None
    return XtbZipExport(
        path=path,
        client_id=match.group("client"),
        period_start=date.fromisoformat(match.group("start")),
        period_end=date.fromisoformat(match.group("end")),
    )


def _sha256_bytes(payload: bytes) -> str:
    digest = hashlib.sha256()
    with BytesIO(payload) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iterator(name: str) -> int:
    match = re.search(r" \((\d+)\)\.zip$", name)
    return int(match.group(1)) if match else 0
