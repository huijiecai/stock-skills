from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from trading_engine.market.context_models import (
    CatalystEvidence,
    DecisionContext,
    DecisionContextRecord,
    PriorDecisionContext,
    ReasoningRecord,
    ToolCallRecord,
)
from trading_engine.errors import ContextError, StorageError
from trading_engine.store.models import JudgmentReport


EVIDENCE_KINDS = {"announcement", "news", "industry", "policy", "other"}
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

    def list_contexts_before(
        self,
        account_name: str,
        before: datetime,
        limit: int = 240,
    ) -> tuple[DecisionContextRecord, ...]:
        if limit < 1:
            raise ContextError("context history limit must be at least one")
        cutoff = _as_utc(before, "before")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT context_snapshots.*
                FROM context_snapshots
                JOIN accounts ON accounts.id = context_snapshots.account_id
                WHERE accounts.name = ? AND context_snapshots.as_of < ?
                ORDER BY context_snapshots.as_of DESC
                LIMIT ?
                """,
                (account_name.strip(), cutoff.isoformat(), limit),
            ).fetchall()
        return tuple(reversed(tuple(_context_record_from_row(row) for row in rows)))

    def list_prior_decisions(
        self,
        account_name: str,
        before: datetime,
        limit: int = 100,
    ) -> tuple[PriorDecisionContext, ...]:
        if limit < 1:
            raise ContextError("decision history limit must be at least one")
        cutoff = _as_utc(before, "before")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT judgments.output_json, context_snapshots.as_of
                FROM judgments
                JOIN context_snapshots
                  ON context_snapshots.id = json_extract(
                      judgments.input_json, '$.decision_context_id'
                  )
                JOIN accounts ON accounts.id = context_snapshots.account_id
                WHERE accounts.name = ?
                  AND context_snapshots.as_of < ?
                  AND judgments.status = 'completed'
                  AND judgments.output_json IS NOT NULL
                ORDER BY context_snapshots.as_of DESC, judgments.created_at DESC
                LIMIT ?
                """,
                (account_name.strip(), cutoff.isoformat(), limit),
            ).fetchall()
        decisions = []
        for row in reversed(rows):
            report = JudgmentReport.model_validate_json(row["output_json"])
            for proposal in report.proposals:
                decisions.append(
                    PriorDecisionContext(
                        as_of=datetime.fromisoformat(row["as_of"]),
                        code=proposal.code,
                        action=proposal.action,
                        quantity=proposal.quantity,
                        reason=proposal.reason,
                    )
                )
        return tuple(decisions)

    def add_reasoning(
        self,
        context_id: str,
        observed: str,
        hypothesis: str,
        verified: str,
        conclusion: str,
    ) -> ReasoningRecord:
        """Append one immutable LLM reasoning chain to a decision context."""
        normalized = {
            "observed": observed.strip(),
            "hypothesis": hypothesis.strip(),
            "verified": verified.strip(),
            "conclusion": conclusion.strip(),
        }
        for field, value in normalized.items():
            if not value:
                raise ContextError(f"reasoning {field} cannot be empty")
        reasoning_id = uuid4().hex
        created_at = datetime.now(UTC)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM context_snapshots WHERE id = ?", (context_id,)
            ).fetchone()
            if existing is None:
                raise StorageError(
                    f"decision context does not exist: {context_id}"
                )
            connection.execute(
                """
                INSERT INTO reasoning_records (
                    id, context_id, observed, hypothesis, verified,
                    conclusion, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reasoning_id,
                    context_id,
                    normalized["observed"],
                    normalized["hypothesis"],
                    normalized["verified"],
                    normalized["conclusion"],
                    created_at.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM reasoning_records WHERE id = ?", (reasoning_id,)
            ).fetchone()
        return _reasoning_from_row(row)

    def list_reasoning(
        self, context_id: str | None = None
    ) -> tuple[ReasoningRecord, ...]:
        query = "SELECT * FROM reasoning_records"
        parameters: tuple[str, ...] = ()
        if context_id is not None:
            query += " WHERE context_id = ?"
            parameters = (context_id,)
        query += " ORDER BY created_at, id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_reasoning_from_row(row) for row in rows)

    def get_context_by_date(
        self,
        account_name: str,
        trading_date: date,
        until_time: str | None = None,
    ) -> DecisionContextRecord | None:
        """Return the context closest to *until_time* on *trading_date*.

        If *until_time* is None, returns the latest context of that date.
        All times are interpreted in Asia/Shanghai timezone.
        """
        from datetime import time as dtime, timedelta
        from zoneinfo import ZoneInfo

        shanghai = ZoneInfo("Asia/Shanghai")
        day_start = datetime.combine(
            trading_date, dtime(0, 0), tzinfo=shanghai
        ).astimezone(UTC)
        day_end = day_start + timedelta(days=1)
        if until_time is not None:
            hh, mm = until_time.split(":")
            cutoff = datetime.combine(
                trading_date, dtime(int(hh), int(mm)), tzinfo=shanghai
            ).astimezone(UTC)
            cutoff = cutoff.replace(second=59, microsecond=999999)
        else:
            cutoff = day_end
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT context_snapshots.*
                FROM context_snapshots
                JOIN accounts ON accounts.id = context_snapshots.account_id
                WHERE accounts.name = ?
                  AND context_snapshots.as_of >= ?
                  AND context_snapshots.as_of < ?
                  AND context_snapshots.as_of <= ?
                ORDER BY context_snapshots.as_of DESC
                LIMIT 1
                """,
                (
                    account_name.strip(),
                    day_start.isoformat(),
                    day_end.isoformat(),
                    cutoff.isoformat(),
                ),
            ).fetchone()
        return _context_record_from_row(row) if row is not None else None

    def add_tool_call(
        self,
        context_id: str,
        tool: str,
        arguments: str,
        result: str,
    ) -> ToolCallRecord:
        """Record one immutable astock tool call attached to a context."""
        normalized_tool = tool.strip()
        normalized_args = arguments.strip()
        normalized_result = result.strip()
        if not normalized_tool:
            raise ContextError("tool call tool name cannot be empty")
        if not normalized_args or not normalized_result:
            raise ContextError("tool call arguments and result cannot be empty")
        call_id = uuid4().hex
        created_at = datetime.now(UTC)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM context_snapshots WHERE id = ?", (context_id,)
            ).fetchone()
            if existing is None:
                raise StorageError(
                    f"decision context does not exist: {context_id}"
                )
            connection.execute(
                """
                INSERT INTO tool_call_records (
                    id, context_id, tool, arguments, result, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    call_id,
                    context_id,
                    normalized_tool,
                    normalized_args,
                    normalized_result,
                    created_at.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM tool_call_records WHERE id = ?", (call_id,)
            ).fetchone()
        return _tool_call_from_row(row)

    def list_tool_calls(
        self, context_id: str | None = None
    ) -> tuple[ToolCallRecord, ...]:
        query = "SELECT * FROM tool_call_records"
        parameters: tuple[str, ...] = ()
        if context_id is not None:
            query += " WHERE context_id = ?"
            parameters = (context_id,)
        query += " ORDER BY created_at, id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_tool_call_from_row(row) for row in rows)

    def _migrate_evidence_table(self, connection: sqlite3.Connection) -> None:
        """Rebuild catalyst_evidence if the CHECK constraint still allows 'market'.

        Also patches old context_snapshots.context_json blobs that still
        contain ``"kind":"market"`` evidence, replacing them with ``"kind":"other"``.
        """
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='catalyst_evidence'"
        ).fetchone()
        if schema is not None and "'market'" in (schema["sql"] or ""):
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS catalyst_evidence_new (
                    id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(id),
                    kind TEXT NOT NULL CHECK (
                        kind IN ('announcement', 'news', 'industry', 'policy', 'other')
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
                INSERT INTO catalyst_evidence_new (
                    id, thesis_id, kind, source_name, source_url,
                    published_at, observed_at, summary, stance,
                    reliability, created_at
                )
                SELECT
                    id, thesis_id,
                    CASE WHEN kind = 'market' THEN 'other' ELSE kind END,
                    source_name, source_url,
                    published_at, observed_at, summary, stance,
                    reliability, created_at
                FROM catalyst_evidence;
                DROP TABLE catalyst_evidence;
                ALTER TABLE catalyst_evidence_new RENAME TO catalyst_evidence;
                """
            )

    def _initialize(self) -> None:
        with self._connect() as connection:
            self._migrate_evidence_table(connection)
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS catalyst_evidence (
                    id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(id),
                    kind TEXT NOT NULL CHECK (
                        kind IN ('announcement', 'news', 'industry', 'policy', 'other')
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
                    market_snapshot_id TEXT NOT NULL,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    as_of TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reasoning_records (
                    id TEXT PRIMARY KEY,
                    context_id TEXT NOT NULL REFERENCES context_snapshots(id),
                    observed TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    verified TEXT NOT NULL,
                    conclusion TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tool_call_records (
                    id TEXT PRIMARY KEY,
                    context_id TEXT NOT NULL REFERENCES context_snapshots(id),
                    tool TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            # Patch old context_json blobs that still contain kind=market evidence
            rows = connection.execute(
                "SELECT id, context_json FROM context_snapshots "
                "WHERE context_json LIKE '%\"kind\":\"market\"%'"
            ).fetchall()
            for row in rows:
                patched = row["context_json"].replace(
                    '"kind":"market"', '"kind":"other"'
                )
                connection.execute(
                    "UPDATE context_snapshots SET context_json = ? WHERE id = ?",
                    (patched, row["id"]),
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


def _reasoning_from_row(row: sqlite3.Row) -> ReasoningRecord:
    return ReasoningRecord(
        id=row["id"],
        context_id=row["context_id"],
        observed=row["observed"],
        hypothesis=row["hypothesis"],
        verified=row["verified"],
        conclusion=row["conclusion"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _tool_call_from_row(row: sqlite3.Row) -> ToolCallRecord:
    return ToolCallRecord(
        id=row["id"],
        context_id=row["context_id"],
        tool=row["tool"],
        arguments=row["arguments"],
        result=row["result"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
