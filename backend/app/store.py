"""Tiny SQLite store: each table holds JSON documents plus a couple of indexed columns."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .models import Campaign, Clip, Job, Submission

M = TypeVar("M", bound=BaseModel)

# table -> (model, indexed parent column or None)
TABLES: dict[str, tuple[type[BaseModel], str | None]] = {
    "campaigns": (Campaign, None),
    "jobs": (Job, "campaign_id"),
    "clips": (Clip, "job_id"),
    "submissions": (Submission, "clip_id"),
}


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.jobs_dir = data_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(data_dir / "clippy.db", check_same_thread=False)
        with self._lock:
            for table, (_, parent) in TABLES.items():
                parent_col = f", {parent} TEXT" if parent else ""
                self._db.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, created REAL, data TEXT{parent_col})"
                )
                if parent:
                    self._db.execute(f"CREATE INDEX IF NOT EXISTS {table}_{parent} ON {table}({parent})")
            self._db.commit()

    def job_dir(self, job_id: str) -> Path:
        path = self.jobs_dir / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, table: str, obj: BaseModel) -> None:
        _, parent = TABLES[table]
        cols = ["id", "created", "data"] + ([parent] if parent else [])
        created = getattr(obj, "created_at", None) or getattr(obj, "updated_at", 0.0)
        values = [obj.id, created, obj.model_dump_json()] + ([getattr(obj, parent)] if parent else [])
        placeholders = ", ".join("?" for _ in cols)
        with self._lock:
            # Keep the original insert time so list order stays stable across updates.
            self._db.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(id) DO UPDATE SET data=excluded.data"
                + (f", {parent}=excluded.{parent}" if parent else ""),
                values,
            )
            self._db.commit()

    def get(self, table: str, obj_id: str) -> BaseModel | None:
        model, _ = TABLES[table]
        with self._lock:
            row = self._db.execute(f"SELECT data FROM {table} WHERE id = ?", (obj_id,)).fetchone()
        return model.model_validate_json(row[0]) if row else None

    def list(self, table: str, parent_id: str | None = None) -> list:
        model, parent = TABLES[table]
        query = f"SELECT data FROM {table}"
        args: tuple = ()
        if parent_id is not None and parent:
            query += f" WHERE {parent} = ?"
            args = (parent_id,)
        query += " ORDER BY created DESC"
        with self._lock:
            rows = self._db.execute(query, args).fetchall()
        return [model.model_validate_json(r[0]) for r in rows]

    def delete(self, table: str, obj_id: str) -> None:
        with self._lock:
            self._db.execute(f"DELETE FROM {table} WHERE id = ?", (obj_id,))
            self._db.commit()

    def clips_for_job(self, job_id: str) -> list[Clip]:
        clips = self.list("clips", job_id)
        return sorted(clips, key=lambda c: c.rank)
