from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from trading_engine.context_models import (
    CatalystEvidence,
    DecisionContext,
    DecisionContextRecord,
)
from trading_engine.errors import ContextError, StorageError


EVIDENCE_KINDS = {"announcement", "news", "industry", "market", "other"}
EVIDENCE_STANCES = {"supports", "contradicts", "neutral"}
EVIDENCE_RELIABILITIES = {"low", "medium", "high"}


class ContextStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add_evidence(
        self,
        thesis_key: str,
        kind: str,
        source_name: str,
        published_at: datetime,
        observed_at: datetime,
        summary: str,
        stance: str,
        reliability: str,
        source_url: str | None = None,
    ) -> CatalystEvidence:
        if kind not in EVIDENCE_KINDS:
            raise ContextError(f"invalid evidence kind: {kind}")
        if stance not in EVIDENCE_STANCES:
            raise ContextError(f"invalid evidence stance: {stance}")
        if reliability not in EVIDENCE_RELIABILITIES:
            raise ContextError(f"invalid evidence reliability: {reliability}")
        normalized_source = source_name.strip()
        normalized_summary = summary.strip()
        if not normalized_source or not normalized_summary:
            raise ContextError("evidence source and summary cannot be empty")
        published = _as_utc(published_at, "published_at")
        observed = _as_utc(observed_at, "observed_at")
        if published > observed:
            raise ContextError("published_at cannot be later than observed_at")

        evidence_id = uuid4().hex
        created_at = datetime.now(UTC)
        with self._connect() as connection:
            thesis = connection.execute(
                "SELECT id, key FROM theses WHERE key = ?",
                (thesis_key.strip().lower(),),
            ).fetchone()
            if thesis is None:
                raise StorageError(f"thesis does not exist: {thesis_key.strip()}")
            connection.execute(
                """
                INSERT INTO catalyst_evidence (
                    id, thesis_id, kind, source_name, source_url,
                    published_at, observed_at, summary, stance,
                    reliability, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    thesis["id"],
                    kind,
                    normalized_source,
                    source_url.strip() if source_url else None,
                    published.isoformat(),
                    observed.isoformat(),
                    normalized_summary,
                    stance,
                    reliability,
                    created_at.isoformat(),
                ),
            )
            row = connection.execute(
                """
                SELECT catalyst_evidence.*, theses.key AS thesis_key
                FROM catalyst_evidence
                JOIN theses ON theses.id = catalyst_evidence.thesis_id
                WHERE catalyst_evidence.id = ?
                """,
                (evidence_id,),
            ).fetchone()
        return _evidence_from_row(row)

    def list_evidence(
        self, thesis_keys: tuple[str, ...] | None = None
    ) -> tuple[CatalystEvidence, ...]:
        query = """
            SELECT catalyst_evidence.*, theses.key AS thesis_key
            FROM catalyst_evidence
            JOIN theses ON theses.id = catalyst_evidence.thesis_id
        """
        parameters: tuple[str, ...] = ()
        if thesis_keys is not None:
            normalized = tuple(key.strip().lower() for key in thesis_keys)
            if not normalized:
                return ()
            placeholders = ",".join("?" for _ in normalized)
            query += f" WHERE theses.key IN ({placeholders})"
            parameters = normalized
        query += " ORDER BY observed_at, published_at, catalyst_evidence.id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_evidence_from_row(row) for row in rows)

    def record_context(self, context: DecisionContext) -> DecisionContextRecord:
        canonical = json.dumps(
            context.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM context_snapshots WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing is not None:
                return _context_record_from_row(existing)

            record_id = uuid4().hex
            created_at = datetime.now(UTC)
            connection.execute(
                """
                INSERT INTO context_snapshots (
                    id, fingerprint, market_snapshot_id, account_id,
                    as_of, context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    fingerprint,
                    context.market_snapshot_id,
                    context.account.id,
                    context.as_of.astimezone(UTC).isoformat(),
                    context.model_dump_json(),
                    created_at.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM context_snapshots WHERE id = ?", (record_id,)
            ).fetchone()
        return _context_record_from_row(row)

    def latest_context(self, account_name: str) -> DecisionContextRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT context_snapshots.*
                FROM context_snapshots
                JOIN accounts ON accounts.id = context_snapshots.account_id
                WHERE accounts.name = ?
                ORDER BY context_snapshots.created_at DESC
                LIMIT 1
                """,
                (account_name.strip(),),
            ).fetchone()
        return _context_record_from_row(row) if row is not None else None

    def get_context(self, context_id: str) -> DecisionContextRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM context_snapshots WHERE id = ?", (context_id,)
            ).fetchone()
        if row is None:
            raise StorageError(f"decision context does not exist: {context_id}")
        return _context_record_from_row(row)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS catalyst_evidence (
                    id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(id),
                    kind TEXT NOT NULL CHECK (
                        kind IN ('announcement', 'news', 'industry', 'market', 'other')
                    ),
                    source_name TEXT NOT NULL,
                    source_url TEXT,
                    published_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    stance TEXT NOT NULL CHECK (
                        stance IN ('supports', 'contradicts', 'neutral')
                    ),
                    reliability TEXT NOT NULL CHECK (
                        reliability IN ('low', 'medium', 'high')
                    ),
                    created_at TEXT NOT NULL,
                    CHECK (published_at <= observed_at)
                );

                CREATE TABLE IF NOT EXISTS context_snapshots (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    market_snapshot_id TEXT NOT NULL REFERENCES live_snapshots(id),
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    as_of TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _as_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ContextError(f"{field} must include a timezone")
    return value.astimezone(UTC)


def _evidence_from_row(row: sqlite3.Row) -> CatalystEvidence:
    return CatalystEvidence(
        id=row["id"],
        thesis_id=row["thesis_id"],
        thesis_key=row["thesis_key"],
        kind=row["kind"],
        source_name=row["source_name"],
        source_url=row["source_url"],
        published_at=datetime.fromisoformat(row["published_at"]),
        observed_at=datetime.fromisoformat(row["observed_at"]),
        summary=row["summary"],
        stance=row["stance"],
        reliability=row["reliability"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _context_record_from_row(row: sqlite3.Row) -> DecisionContextRecord:
    return DecisionContextRecord(
        id=row["id"],
        fingerprint=row["fingerprint"],
        context=DecisionContext.model_validate_json(row["context_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
