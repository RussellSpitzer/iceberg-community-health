# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from iceberg_community_health.schema import COLUMNS, PRIMARY_KEYS, TABLES


class Store:
    """Append-only Parquet snapshots for one project.

    A failed collection does not write a part file. Readers keep the previous
    parts, and `last_good` stays on the last successful run for that source.
    """

    def __init__(self, root: Path, project_id: str) -> None:
        self.root = Path(root) / "projects" / project_id
        self.root.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        source: str,
        table: str,
        rows: list[dict],
        run_id: str,
        collected_at: str,
    ) -> Path | None:
        if table not in TABLES:
            raise ValueError(f"Unknown table {table}")
        stamped = []
        for row in rows:
            item = {column: _cell(row.get(column)) for column in COLUMNS[table]}
            item["run_id"] = run_id
            item["collected_at"] = collected_at
            stamped.append(item)
        if not stamped:
            return None
        day = collected_at[:10]
        directory = self.root / "raw" / source / table / f"date={day}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"part-{run_id}.parquet"
        _write_parquet(table, stamped, path)
        return path

    def read(self, table: str) -> list[dict]:
        files = sorted(self.root.glob(f"raw/*/{table}/date=*/part-*.parquet"))
        if not files:
            return []
        return _dedupe(table, _read_parquet(files))

    def mark_good(self, source: str, run_id: str, watermark: str | None = None) -> None:
        state = self._watermarks()
        current = state.get(source, {})
        current["last_good_run"] = run_id
        if watermark is not None:
            current["watermark"] = watermark
        state[source] = current
        self._write_watermarks(state)

    def last_good(self, source: str) -> str | None:
        return self._watermarks().get(source, {}).get("last_good_run")

    def write_manifest(self, run_id: str, manifest: dict) -> Path:
        directory = self.root / "manifests"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{run_id}.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return path

    def write_metrics(self, run_id: str, rows: list[dict]) -> Path:
        directory = self.root / "snapshots" / run_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "metrics.parquet"
        _write_metrics_parquet(rows, path)
        return path

    def _watermarks(self) -> dict:
        path = self.root / "state" / "watermarks.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text())

    def _write_watermarks(self, state: dict) -> None:
        directory = self.root / "state"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "watermarks.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n"
        )


def _cell(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_parquet(table: str, rows: list[dict], path: Path) -> None:
    columns = COLUMNS[table]
    connection = duckdb.connect()
    _insert(connection, "snapshot", columns, rows)
    connection.execute(f"COPY snapshot TO '{_sql_path(path)}' (FORMAT PARQUET)")
    connection.close()


def _write_metrics_parquet(rows: list[dict], path: Path) -> None:
    columns = (
        "metric_id",
        "definition_version",
        "scope_type",
        "scope_id",
        "window_start",
        "window_end",
        "value",
        "flag",
        "population_count",
        "tier",
    )
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE metrics (
          metric_id VARCHAR,
          definition_version VARCHAR,
          scope_type VARCHAR,
          scope_id VARCHAR,
          window_start VARCHAR,
          window_end VARCHAR,
          value DOUBLE,
          flag VARCHAR,
          population_count BIGINT,
          tier VARCHAR
        )
        """
    )
    if rows:
        connection.executemany(
            "INSERT INTO metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(row.get(column) for column in columns) for row in rows],
        )
    connection.execute(f"COPY metrics TO '{_sql_path(path)}' (FORMAT PARQUET)")
    connection.close()


def _read_parquet(files: list[Path]) -> list[dict]:
    connection = duckdb.connect()
    listed = ", ".join(f"'{_sql_path(path)}'" for path in files)
    cursor = connection.execute(f"SELECT * FROM read_parquet([{listed}])")
    names = [item[0] for item in cursor.description]
    rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
    connection.close()
    return rows


def _insert(connection, name: str, columns: tuple[str, ...], rows: list[dict]) -> None:
    definitions = ", ".join(f"{column} VARCHAR" for column in columns)
    connection.execute(f"CREATE TABLE {name} ({definitions})")
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {name} VALUES ({placeholders})",
        [tuple(row.get(column) for column in columns) for row in rows],
    )


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _dedupe(table: str, rows: list[dict]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for row in rows:
        key = tuple(row.get(column) for column in PRIMARY_KEYS[table])
        current = best.get(key)
        if current is None or (row.get("collected_at") or "") >= (current.get("collected_at") or ""):
            best[key] = row
    return list(best.values())
