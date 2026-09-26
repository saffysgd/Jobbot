"""PostgreSQL-backed storage for published job applications."""

import os
from typing import Any, Dict, Optional

import psycopg
from psycopg.types.json import Jsonb


class JobStore:
    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            raise ValueError("DATABASE_URL не задан: укажите URL базы PostgreSQL.")

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, connect_timeout=10)

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    message_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    text TEXT NOT NULL,
                    admin_msg_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save(self, message_id: str, job: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (message_id, status, text, admin_msg_ids)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (message_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    text = EXCLUDED.text,
                    admin_msg_ids = EXCLUDED.admin_msg_ids,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    str(message_id),
                    job["status"],
                    job["text"],
                    Jsonb(job.get("admin_msg_ids", {})),
                ),
            )

    def get(self, message_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status, text, admin_msg_ids
                FROM jobs
                WHERE message_id = %s
                """,
                (str(message_id),),
            ).fetchone()

        if row is None:
            return None

        return {
            "status": row[0],
            "text": row[1],
            "admin_msg_ids": row[2],
        }