"""Database helpers for the FastAPI backend."""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - only needed when DATABASE_URL uses Postgres.
    psycopg2 = None
    RealDictCursor = None


class Cursor:
    def __init__(self, cursor: Any, *, lastrowid: int | None = None) -> None:
        self._cursor = cursor
        self.lastrowid = (
            lastrowid if lastrowid is not None else getattr(cursor, "lastrowid", None)
        )

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()


class Connection:
    def __init__(self, raw: Any, dialect: str) -> None:
        self._raw = raw
        self.dialect = dialect

    def execute(self, query: str, params: tuple = ()) -> Cursor:
        if self.dialect == "postgres":
            return self._execute_postgres(query, params)
        return Cursor(self._raw.execute(query, params))

    def _execute_postgres(self, query: str, params: tuple = ()) -> Cursor:
        translated = _translate_postgres_query(query)
        returning_id = _is_insert_values_without_returning(translated)
        if returning_id:
            translated = f"{translated.rstrip()} RETURNING id"

        cursor = self._raw.cursor()
        cursor.execute(translated, params)

        lastrowid = None
        if returning_id:
            row = cursor.fetchone()
            if row is not None:
                lastrowid = int(row["id"])
        return Cursor(cursor, lastrowid=lastrowid)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


def _database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def _db_path() -> Path:
    configured = os.getenv("BACKEND_DB_PATH", "./data/backend.db")
    path = Path(configured)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _open_connection() -> Connection:
    database_url = _database_url()
    if database_url:
        if psycopg2 is None or RealDictCursor is None:
            raise RuntimeError(
                "DATABASE_URL requires psycopg2. Install psycopg2-binary."
            )
        raw_conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        return Connection(raw_conn, "postgres")

    raw_conn = sqlite3.connect(_db_path())
    raw_conn.row_factory = sqlite3.Row
    conn = Connection(raw_conn, "sqlite")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _translate_postgres_query(query: str) -> str:
    translated = query.replace("?", "%s")
    translated = re.sub(
        r"datetime\('now'\)",
        "CURRENT_TIMESTAMP::text",
        translated,
        flags=re.IGNORECASE,
    )
    translated = translated.replace(
        "INTEGER PRIMARY KEY AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
    )
    return translated


def _is_insert_values_without_returning(query: str) -> bool:
    normalized = query.strip()
    return (
        normalized.upper().startswith("INSERT ")
        and re.search(r"\bVALUES\b", normalized, flags=re.IGNORECASE) is not None
        and re.search(r"\bRETURNING\b", normalized, flags=re.IGNORECASE) is None
    )


@contextmanager
def connect() -> Iterator[Connection]:
    conn = _open_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[Connection]:
    conn = _open_connection()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_in_transaction(work: Callable[[Connection], Any]) -> Any:
    with transaction() as conn:
        return work(conn)


def _table_columns(conn: Connection, table_name: str) -> set[str]:
    if conn.dialect == "postgres":
        rows = conn.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        ).fetchall()
        return {str(row["name"]) for row in rows}

    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _table_info(conn: Connection, table_name: str) -> list[dict[str, Any]]:
    if conn.dialect == "postgres":
        rows = conn.execute(
            """
            SELECT column_name AS name,
                   CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        ).fetchall()
        return [dict(row) for row in rows]

    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [dict(row) for row in rows]


def _ensure_column(
    conn: Connection, table_name: str, column_name: str, definition: str
) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _create_indexes(conn: Connection) -> None:
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_slug
        ON tenants (slug)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
        ON users (email)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_tenant_role
        ON users (tenant_id, role, is_active)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_assets_portfolio_created
        ON assets (portfolio_id, created_at DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_transactions_portfolio_timestamp
        ON transactions (portfolio_id, timestamp DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alerts_portfolio_created
        ON alerts (portfolio_id, created_at DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_risk_assessments_portfolio_created
        ON risk_assessments (portfolio_id, created_at DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_trends_symbol_timestamp
        ON market_trends (symbol, timestamp DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_timestamp
        ON audit_logs (tenant_id, timestamp DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_logs_resource
        ON audit_logs (resource, resource_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_analyses_portfolio_created
        ON analyses (portfolio_id, created_at DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_analyses_type_created
        ON analyses (portfolio_id, analysis_type, created_at DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_analyses_vector_document
        ON analyses (vector_document_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cases_portfolio_status_created
        ON cases (portfolio_id, status, created_at DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cases_tenant_state_opened
        ON cases (tenant_id, state, opened_at DESC, id DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cases_transaction
        ON cases (transaction_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cases_assignee
        ON cases (assignee_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_case_events_case_created
        ON case_events (case_id, created_at DESC, id DESC)
        """
    )


def _migrate_schema(conn: Connection) -> None:
    _ensure_column(conn, "assets", "updated_at", "TEXT NOT NULL DEFAULT ''")

    _ensure_column(conn, "alerts", "triggered_at", "TEXT")

    _ensure_column(conn, "analyses", "summary", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "analyses", "search_text", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "analyses", "metadata", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "analyses", "vector_collection", "TEXT")
    _ensure_column(conn, "analyses", "vector_document_id", "TEXT")
    _ensure_column(conn, "analyses", "updated_at", "TEXT NOT NULL DEFAULT ''")

    _ensure_column(conn, "cases", "tenant_id", "INTEGER")
    _ensure_column(conn, "cases", "alert_id", "INTEGER")
    _ensure_column(conn, "cases", "title", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "cases", "subject_user", "TEXT")
    _ensure_column(conn, "cases", "summary", "TEXT")
    _ensure_column(conn, "cases", "priority", "TEXT NOT NULL DEFAULT 'medium'")
    _ensure_column(conn, "cases", "risk_label", "TEXT")
    _ensure_column(conn, "cases", "symbol", "TEXT")
    _ensure_column(conn, "cases", "amount", "REAL")
    _ensure_column(
        conn, "cases", "source", "TEXT NOT NULL DEFAULT 'transaction_monitoring'"
    )
    _ensure_column(conn, "cases", "metadata", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "cases", "state", "TEXT NOT NULL DEFAULT 'new'")
    _ensure_column(conn, "cases", "assignee_id", "INTEGER")
    _ensure_column(conn, "cases", "opened_at", "TEXT")
    _ensure_column(conn, "cases", "closed_at", "TEXT")
    _ensure_column(conn, "cases", "sla_due_at", "TEXT")
    _ensure_column(conn, "cases", "ai_analysis", "TEXT")
    _ensure_column(conn, "cases", "notes", "TEXT")
    _ensure_column(conn, "cases", "updated_at", "TEXT NOT NULL DEFAULT ''")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            body TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (case_id) REFERENCES cases(id)
        )
        """
    )
    _ensure_column(conn, "case_events", "actor_user_id", "INTEGER")
    _ensure_column(conn, "case_events", "actor_email", "TEXT")
    _ensure_column(conn, "case_events", "from_state", "TEXT")
    _ensure_column(conn, "case_events", "to_state", "TEXT")
    _ensure_column(conn, "case_events", "data", "TEXT")
    _ensure_column(conn, "case_events", "timestamp", "TEXT")

    _create_indexes(conn)


def _rebuild_cases_table_if_needed(conn: Connection) -> None:
    if conn.dialect == "postgres":
        return

    columns = {row["name"]: row for row in _table_info(conn, "cases")}
    portfolio_notnull = bool(columns.get("portfolio_id", {}).get("notnull"))
    transaction_notnull = bool(columns.get("transaction_id", {}).get("notnull"))
    if not portfolio_notnull and not transaction_notnull:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(
            """
            CREATE TABLE cases__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER,
                portfolio_id INTEGER,
                transaction_id INTEGER,
                alert_id INTEGER,
                title TEXT NOT NULL DEFAULT '',
                subject_user TEXT,
                summary TEXT,
                risk_score REAL NOT NULL,
                risk_label TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                symbol TEXT,
                amount REAL,
                flags TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'open',
                source TEXT NOT NULL DEFAULT 'transaction_monitoring',
                metadata TEXT NOT NULL DEFAULT '{}',
                state TEXT NOT NULL DEFAULT 'new',
                assignee_id INTEGER,
                opened_at TEXT,
                closed_at TEXT,
                sla_due_at TEXT,
                ai_analysis TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                FOREIGN KEY (transaction_id) REFERENCES transactions(id),
                FOREIGN KEY (assignee_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO cases__new (
                id, tenant_id, portfolio_id, transaction_id, alert_id, title,
                subject_user, summary, risk_score, risk_label, priority, symbol,
                amount, flags, status, source, metadata, state, assignee_id,
                opened_at, closed_at, sla_due_at, ai_analysis, notes, created_at, updated_at
            )
            SELECT
                id, tenant_id, portfolio_id, transaction_id, alert_id, title,
                subject_user, summary, risk_score, risk_label, priority, symbol,
                amount, flags, status, source, metadata, state, assignee_id,
                opened_at, closed_at, sla_due_at, ai_analysis, notes, created_at, updated_at
            FROM cases
            """
        )
        conn.execute("DROP TABLE cases")
        conn.execute("ALTER TABLE cases__new RENAME TO cases")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    _create_indexes(conn)


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                role TEXT NOT NULL DEFAULT 'analyst',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login TEXT,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                total_value REAL NOT NULL DEFAULT 0,
                cash_balance REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL DEFAULT 0,
                purchase_price REAL NOT NULL DEFAULT 0,
                current_price REAL NOT NULL DEFAULT 0,
                asset_type TEXT NOT NULL DEFAULT 'stock',
                sector TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                total_amount REAL NOT NULL,
                fees REAL NOT NULL DEFAULT 0,
                notes TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                alert_type TEXT NOT NULL,
                symbol TEXT,
                target_price REAL,
                threshold REAL,
                message TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                triggered INTEGER NOT NULL DEFAULT 0,
                triggered_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                risk_score REAL,
                volatility REAL,
                concentration_risk REAL,
                fraud_risk REAL,
                liquidity_risk REAL,
                assessment_data TEXT NOT NULL DEFAULT '{}',
                recommendation TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                analysis_type TEXT,
                trend_direction TEXT,
                confidence REAL,
                analysis_data TEXT NOT NULL DEFAULT '{}',
                timestamp TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER,
                user_id TEXT,
                user_email TEXT,
                action TEXT NOT NULL,
                resource TEXT,
                resource_id TEXT,
                details TEXT NOT NULL DEFAULT '{}',
                ip_address TEXT,
                user_agent TEXT,
                timestamp TEXT NOT NULL,
                prev_hash TEXT,
                entry_hash TEXT,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                analysis_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                search_text TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                vector_collection TEXT,
                vector_document_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER,
                portfolio_id INTEGER NOT NULL,
                transaction_id INTEGER NOT NULL,
                alert_id INTEGER,
                title TEXT NOT NULL DEFAULT '',
                subject_user TEXT,
                summary TEXT,
                risk_score REAL NOT NULL,
                risk_label TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                symbol TEXT,
                amount REAL,
                flags TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'open',
                source TEXT NOT NULL DEFAULT 'transaction_monitoring',
                metadata TEXT NOT NULL DEFAULT '{}',
                state TEXT NOT NULL DEFAULT 'new',
                assignee_id INTEGER,
                opened_at TEXT,
                closed_at TEXT,
                sla_due_at TEXT,
                ai_analysis TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                FOREIGN KEY (transaction_id) REFERENCES transactions(id),
                FOREIGN KEY (assignee_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                actor_user_id INTEGER,
                actor_email TEXT,
                from_state TEXT,
                to_state TEXT,
                body TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                data TEXT,
                timestamp TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES cases(id),
                FOREIGN KEY (actor_user_id) REFERENCES users(id)
            )
            """
        )
        _migrate_schema(conn)
        _rebuild_cases_table_if_needed(conn)
        _bootstrap_compat_data(conn)


def fetch_one(
    query: str, params: tuple = (), *, conn: Connection | None = None
) -> dict | None:
    if conn is not None:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None
    with connect() as local_conn:
        row = local_conn.execute(query, params).fetchone()
    return dict(row) if row else None


def fetch_all(
    query: str, params: tuple = (), *, conn: Connection | None = None
) -> list[dict]:
    if conn is not None:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    with connect() as local_conn:
        rows = local_conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def execute(query: str, params: tuple = (), *, conn: Connection | None = None) -> int:
    if conn is not None:
        cursor = conn.execute(query, params)
        return int(cursor.lastrowid)
    with connect() as local_conn:
        cursor = local_conn.execute(query, params)
        return int(cursor.lastrowid)


def _bootstrap_compat_data(conn: Connection) -> None:
    tenant = conn.execute(
        "SELECT id FROM tenants WHERE slug = ?",
        ("default",),
    ).fetchone()
    if tenant is None:
        tenant_id = int(
            conn.execute(
                "INSERT INTO tenants (slug, name, created_at) VALUES (?, ?, datetime('now'))",
                ("default", "Default"),
            ).lastrowid
        )
    else:
        tenant_id = int(tenant["id"])

    conn.execute(
        """
        UPDATE cases
        SET tenant_id = COALESCE(tenant_id, ?),
            state = CASE
                WHEN COALESCE(state, '') = '' THEN
                    CASE WHEN COALESCE(status, 'open') = 'open' THEN 'new' ELSE status END
                ELSE state
            END,
            opened_at = COALESCE(opened_at, created_at),
            updated_at = CASE WHEN updated_at = '' THEN created_at ELSE updated_at END
        """,
        (tenant_id,),
    )
    conn.execute(
        """
        UPDATE case_events
        SET timestamp = COALESCE(NULLIF(timestamp, ''), created_at)
        """
    )
    conn.execute(
        """
        UPDATE assets
        SET updated_at = CASE WHEN updated_at = '' THEN created_at ELSE updated_at END
        """
    )
