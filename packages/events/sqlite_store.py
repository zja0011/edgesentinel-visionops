"""SQLite event persistence and dependency-free history queries."""

import json
import os
import sqlite3


class SqliteEventStore(object):
    def __init__(self, path, read_only=False):
        self.path = os.path.abspath(path)
        self.read_only = bool(read_only)
        parent = os.path.dirname(self.path)
        if self.read_only and not os.path.isfile(self.path):
            raise OSError("event database does not exist: {0}".format(
                self.path
            ))
        if not self.read_only and not os.path.isdir(parent):
            os.makedirs(parent)

        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        if self.read_only:
            self._connection.execute("PRAGMA query_only=ON")
        else:
            self._initialize()

    def _initialize(self):
        with self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    frame_id INTEGER NOT NULL,
                    camera_id TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    zone_name TEXT NOT NULL,
                    track_id INTEGER,
                    object_class TEXT NOT NULL,
                    evidence_path TEXT,
                    details_json TEXT NOT NULL
                )
                """
            )
            self._ensure_column(
                "status",
                "TEXT NOT NULL DEFAULT 'OPEN'",
            )
            self._ensure_column(
                "acknowledged_at",
                "TEXT",
            )
            self._ensure_column(
                "acknowledged_by",
                "TEXT",
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_timestamp
                ON events(timestamp)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_type_timestamp
                ON events(event_type, timestamp)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_object_timestamp
                ON events(object_class, timestamp)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_page_order
                ON events(timestamp DESC, frame_id DESC, event_id DESC)
                """
            )

    def _ensure_column(self, name, declaration):
        columns = {
            row["name"]
            for row in self._connection.execute(
                "PRAGMA table_info(events)"
            ).fetchall()
        }
        if name not in columns:
            self._connection.execute(
                "ALTER TABLE events ADD COLUMN {0} {1}".format(
                    name,
                    declaration,
                )
            )

    def append(self, event):
        payload = event.to_dict()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO events (
                    event_id,
                    schema_version,
                    event_type,
                    severity,
                    timestamp,
                    frame_id,
                    camera_id,
                    zone_id,
                    zone_name,
                    track_id,
                    object_class,
                    evidence_path,
                    details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["event_id"],
                    payload["schema_version"],
                    payload["event_type"],
                    payload["severity"],
                    payload["timestamp"],
                    payload["frame_id"],
                    payload["camera_id"],
                    payload["zone_id"],
                    payload["zone_name"],
                    payload["track_id"],
                    payload["object_class"],
                    payload["evidence_path"],
                    json.dumps(
                        payload["details"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )

    def query(
        self,
        limit=50,
        event_type=None,
        object_class=None,
        camera_id=None,
        since_timestamp=None,
        status=None,
        severity=None,
        before=None,
    ):
        limit = int(limit)
        if limit <= 0:
            raise ValueError("limit must be positive")

        clauses = []
        parameters = []
        if event_type:
            clauses.append("event_type = ?")
            parameters.append(str(event_type))
        if object_class:
            clauses.append("object_class = ?")
            parameters.append(str(object_class))
        if camera_id:
            clauses.append("camera_id = ?")
            parameters.append(str(camera_id))
        if status:
            clauses.append("status = ?")
            parameters.append(str(status))
        if severity:
            clauses.append("severity = ?")
            parameters.append(str(severity))
        if since_timestamp:
            clauses.append(
                "julianday(timestamp) >= julianday(?)"
            )
            parameters.append(str(since_timestamp))
        if before is not None:
            if (
                not isinstance(before, (list, tuple))
                or len(before) != 3
            ):
                raise ValueError(
                    "before must contain timestamp, frame_id, event_id"
                )
            before_timestamp = str(before[0])
            before_frame_id = int(before[1])
            before_event_id = str(before[2])
            clauses.append(
                "("
                "timestamp < ? OR "
                "(timestamp = ? AND frame_id < ?) OR "
                "(timestamp = ? AND frame_id = ? "
                "AND event_id < ?)"
                ")"
            )
            parameters.extend(
                [
                    before_timestamp,
                    before_timestamp,
                    before_frame_id,
                    before_timestamp,
                    before_frame_id,
                    before_event_id,
                ]
            )

        sql = "SELECT * FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += (
            " ORDER BY timestamp DESC, frame_id DESC, "
            "event_id DESC LIMIT ?"
        )
        parameters.append(limit)

        rows = self._connection.execute(sql, parameters).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def query_day(
        self,
        date,
        limit=500,
        camera_id=None,
        object_class=None,
    ):
        limit = int(limit)
        if limit <= 0:
            raise ValueError("limit must be positive")
        clauses = ["substr(timestamp, 1, 10) = ?"]
        parameters = [str(date)]
        if camera_id:
            clauses.append("camera_id = ?")
            parameters.append(str(camera_id))
        if object_class:
            clauses.append("object_class = ?")
            parameters.append(str(object_class))
        sql = (
            "SELECT * FROM events WHERE {0} "
            "ORDER BY timestamp DESC, frame_id DESC LIMIT ?"
        ).format(" AND ".join(clauses))
        parameters.append(limit)
        rows = self._connection.execute(sql, parameters).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def summarize(
        self,
        event_type=None,
        object_class=None,
        camera_id=None,
        since_timestamp=None,
        until_timestamp=None,
        status=None,
        severity=None,
        group_limit=20,
    ):
        group_limit = int(group_limit)
        if group_limit <= 0 or group_limit > 100:
            raise ValueError(
                "group_limit must be between 1 and 100"
            )
        clauses = []
        parameters = []
        if event_type:
            clauses.append("event_type = ?")
            parameters.append(str(event_type))
        if object_class:
            clauses.append("object_class = ?")
            parameters.append(str(object_class))
        if camera_id:
            clauses.append("camera_id = ?")
            parameters.append(str(camera_id))
        if status:
            clauses.append("status = ?")
            parameters.append(str(status))
        if severity:
            clauses.append("severity = ?")
            parameters.append(str(severity))
        if since_timestamp:
            clauses.append(
                "julianday(timestamp) >= julianday(?)"
            )
            parameters.append(str(since_timestamp))
        if until_timestamp:
            clauses.append(
                "julianday(timestamp) < julianday(?)"
            )
            parameters.append(str(until_timestamp))
        where_sql = (
            " WHERE " + " AND ".join(clauses)
            if clauses
            else ""
        )
        total = self._connection.execute(
            "SELECT COUNT(*) AS count FROM events" + where_sql,
            parameters,
        ).fetchone()["count"]
        groups = {}
        group_truncated = {}
        for field in (
            "event_type",
            "severity",
            "object_class",
            "zone_id",
        ):
            rows = self._connection.execute(
                (
                    "SELECT {0} AS name, COUNT(*) AS count "
                    "FROM events{1} GROUP BY {0} "
                    "ORDER BY count DESC, name ASC LIMIT ?"
                ).format(field, where_sql),
                parameters + [group_limit + 1],
            ).fetchall()
            group_truncated[field] = len(rows) > group_limit
            groups[field] = [
                {
                    "name": row["name"],
                    "count": int(row["count"]),
                }
                for row in rows[:group_limit]
            ]
        return {
            "total_events": int(total),
            "groups": groups,
            "group_truncated": group_truncated,
        }

    def summarize_timeline(
        self,
        bucket_minutes,
        event_type=None,
        object_class=None,
        camera_id=None,
        since_timestamp=None,
        status=None,
        severity=None,
    ):
        bucket_minutes = int(bucket_minutes)
        if bucket_minutes not in (15, 30, 60):
            raise ValueError(
                "bucket_minutes must be 15, 30, or 60"
            )
        clauses = []
        parameters = []
        if event_type:
            clauses.append("event_type = ?")
            parameters.append(str(event_type))
        if object_class:
            clauses.append("object_class = ?")
            parameters.append(str(object_class))
        if camera_id:
            clauses.append("camera_id = ?")
            parameters.append(str(camera_id))
        if status:
            clauses.append("status = ?")
            parameters.append(str(status))
        if severity:
            clauses.append("severity = ?")
            parameters.append(str(severity))
        if since_timestamp:
            clauses.append(
                "julianday(timestamp) >= julianday(?)"
            )
            parameters.append(str(since_timestamp))
        where_sql = (
            " WHERE " + " AND ".join(clauses)
            if clauses
            else ""
        )
        bucket_sql = (
            "strftime('%Y-%m-%dT%H:', "
            "datetime(timestamp, '+8 hours')) || "
            "printf('%02d', "
            "(CAST(strftime('%M', "
            "datetime(timestamp, '+8 hours')) AS INTEGER) "
            "/ ?) * ?) || ':00+08:00'"
        )
        rows = self._connection.execute(
            (
                "SELECT {0} AS bucket_start, "
                "COUNT(*) AS count FROM events{1} "
                "GROUP BY bucket_start "
                "ORDER BY bucket_start ASC"
            ).format(bucket_sql, where_sql),
            [bucket_minutes, bucket_minutes] + parameters,
        ).fetchall()
        return [
            {
                "start": row["bucket_start"],
                "count": int(row["count"]),
            }
            for row in rows
        ]

    def count_filtered(
        self,
        event_type=None,
        object_class=None,
        camera_id=None,
        since_timestamp=None,
        until_timestamp=None,
        status=None,
        severity=None,
    ):
        clauses = []
        parameters = []
        if event_type:
            clauses.append("event_type = ?")
            parameters.append(str(event_type))
        if object_class:
            clauses.append("object_class = ?")
            parameters.append(str(object_class))
        if camera_id:
            clauses.append("camera_id = ?")
            parameters.append(str(camera_id))
        if status:
            clauses.append("status = ?")
            parameters.append(str(status))
        if severity:
            clauses.append("severity = ?")
            parameters.append(str(severity))
        if since_timestamp:
            clauses.append(
                "julianday(timestamp) >= julianday(?)"
            )
            parameters.append(str(since_timestamp))
        if until_timestamp:
            clauses.append(
                "julianday(timestamp) < julianday(?)"
            )
            parameters.append(str(until_timestamp))
        where_sql = (
            " WHERE " + " AND ".join(clauses)
            if clauses
            else ""
        )
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM events" + where_sql,
            parameters,
        ).fetchone()
        return int(row["count"])

    def count_event_ids(self, event_ids):
        event_ids = list(event_ids)
        if not event_ids:
            return 0
        placeholders = ",".join("?" for unused in event_ids)
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM events "
            "WHERE event_id IN ({0})".format(placeholders),
            event_ids,
        ).fetchone()
        return int(row["count"])

    def count(self):
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM events"
        ).fetchone()
        return int(row["count"])

    def get(self, event_id):
        row = self._connection.execute(
            "SELECT * FROM events WHERE event_id = ?",
            (str(event_id),),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def acknowledge(
        self,
        event_id,
        acknowledged_at,
        acknowledged_by="operator",
    ):
        if self.read_only:
            raise sqlite3.OperationalError(
                "event database is read-only"
            )
        event_id = str(event_id)
        with self._connection:
            row = self._connection.execute(
                "SELECT * FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            previous_status = (
                row["status"]
                if "status" in row.keys()
                else "OPEN"
            )
            already_acknowledged = (
                previous_status == "ACKNOWLEDGED"
            )
            if not already_acknowledged:
                self._connection.execute(
                    """
                    UPDATE events
                    SET status = ?,
                        acknowledged_at = ?,
                        acknowledged_by = ?
                    WHERE event_id = ?
                      AND status != ?
                    """,
                    (
                        "ACKNOWLEDGED",
                        str(acknowledged_at),
                        str(acknowledged_by),
                        event_id,
                        "ACKNOWLEDGED",
                    ),
                )
            updated = self._connection.execute(
                "SELECT * FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        payload = self._row_to_dict(updated)
        payload["already_acknowledged"] = already_acknowledged
        return payload

    @staticmethod
    def _row_to_dict(row):
        columns = set(row.keys())
        return {
            "schema_version": row["schema_version"],
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "severity": row["severity"],
            "timestamp": row["timestamp"],
            "frame_id": row["frame_id"],
            "camera_id": row["camera_id"],
            "zone_id": row["zone_id"],
            "zone_name": row["zone_name"],
            "track_id": row["track_id"],
            "object_class": row["object_class"],
            "evidence_path": row["evidence_path"],
            "details": json.loads(row["details_json"]),
            "status": (
                row["status"]
                if "status" in columns
                else "OPEN"
            ),
            "acknowledged_at": (
                row["acknowledged_at"]
                if "acknowledged_at" in columns
                else None
            ),
            "acknowledged_by": (
                row["acknowledged_by"]
                if "acknowledged_by" in columns
                else None
            ),
        }

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
