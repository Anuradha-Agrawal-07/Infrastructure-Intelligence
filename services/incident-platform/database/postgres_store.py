from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


class DatabaseUnavailable(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresIncidentStore:
    """
    Durable incident store.

    PostgreSQL is the source of truth.
    The API layer should never treat Redis or an in-memory cache
    as the authoritative incident store.
    """

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/infrastructure",
        )

    @contextmanager
    def connection(self):
        if psycopg is None:
            raise DatabaseUnavailable(
                "psycopg is not installed. "
                "Install with: python -m pip install psycopg[binary]"
            )

        connection = psycopg.connect(
            self.dsn,
            row_factory=dict_row,
        )

        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_incident(self, incident) -> dict:
        query = """
            INSERT INTO incidents (
                id,
                title,
                status,
                priority,
                created_at,
                updated_at,
                resolved_at,
                version,
                affected_services,
                primary_suspect,
                confidence
            )
            VALUES (
                %(id)s,
                %(title)s,
                %(status)s,
                %(priority)s,
                %(created_at)s,
                %(updated_at)s,
                %(resolved_at)s,
                %(version)s,
                %(affected_services)s::jsonb,
                %(primary_suspect)s,
                %(confidence)s
            )
            RETURNING *
        """

        values = {
            "id": incident.incident_id,
            "title": incident.title,
            "status": incident.status.value,
            "priority": incident.priority,
            "created_at": incident.created_at,
            "updated_at": incident.updated_at,
            "resolved_at": incident.resolved_at,
            "version": incident.version,
            "affected_services": json.dumps(
                incident.affected_services
            ),
            "primary_suspect": incident.primary_suspect,
            "confidence": incident.confidence,
        }

        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
                return cursor.fetchone()

    def get_incident(self, incident_id: UUID) -> dict | None:
        query = """
            SELECT *
            FROM incidents
            WHERE id = %s
        """

        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (incident_id,))
                return cursor.fetchone()

    def list_incidents(
        self,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[dict]:

        conditions = []
        parameters = []

        if status:
            conditions.append("status = %s")
            parameters.append(status)

        if priority:
            conditions.append("priority = %s")
            parameters.append(priority)

        query = """
            SELECT *
            FROM incidents
        """

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += """
            ORDER BY created_at DESC
        """

        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, parameters)
                return cursor.fetchall()

    def update_status(
        self,
        incident_id: UUID,
        current_version: int,
        status: str,
        resolved_at: datetime | None = None,
    ) -> dict | None:

        query = """
            UPDATE incidents
            SET
                status = %s,
                updated_at = %s,
                resolved_at = %s,
                version = version + 1
            WHERE
                id = %s
                AND version = %s
            RETURNING *
        """

        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        status,
                        utc_now(),
                        resolved_at,
                        incident_id,
                        current_version,
                    ),
                )

                return cursor.fetchone()

    def append_event(
        self,
        incident_id: UUID,
        event_id: UUID,
        event_type: str,
        payload: dict,
        occurred_at: datetime | None = None,
    ) -> dict:

        query = """
            INSERT INTO incident_events (
                id,
                incident_id,
                event_id,
                event_type,
                occurred_at,
                payload
            )
            VALUES (
                gen_random_uuid(),
                %s,
                %s,
                %s,
                %s,
                %s::jsonb
            )
            RETURNING *
        """

        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        incident_id,
                        event_id,
                        event_type,
                        occurred_at or utc_now(),
                        json.dumps(payload),
                    ),
                )

                return cursor.fetchone()

    def get_timeline(
        self,
        incident_id: UUID,
        after_sequence: int = 0,
    ) -> list[dict]:

        query = """
            SELECT *
            FROM incident_events
            WHERE incident_id = %s
              AND sequence > %s
            ORDER BY sequence ASC
        """

        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (incident_id, after_sequence),
                )

                return cursor.fetchall()
