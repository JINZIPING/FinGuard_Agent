from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth import DEFAULT_TENANT_SLUG, register_user  # noqa: E402
from app.db import _db_path, connect, execute, fetch_one, init_db  # noqa: E402
from app.transaction_side_effects import create_transaction_with_side_effects  # noqa: E402


DEMO_USERS = (
    {
        "email": "admin@finguard.demo",
        "password": "FinGuard123!",
        "name": "FinGuard Admin",
        "role": "admin",
    },
    {
        "email": "supervisor@finguard.demo",
        "password": "FinGuard123!",
        "name": "FinGuard Supervisor",
        "role": "supervisor",
    },
    {
        "email": "analyst@finguard.demo",
        "password": "FinGuard123!",
        "name": "FinGuard Analyst",
        "role": "analyst",
    },
)


def _default_db_path() -> str:
    return str(BACKEND_ROOT / "data" / "backend.db")


def _reset_db_if_requested() -> None:
    mode = str(os.getenv("DEMO_SEED", "")).strip().lower()
    if mode not in {"reset", "true", "1"}:
        return

    path = _db_path().resolve()
    allowed_root = (BACKEND_ROOT / "data").resolve()
    if allowed_root not in path.parents and path != allowed_root:
        raise RuntimeError(f"Refusing to reset database outside demo data dir: {path}")
    if path.exists():
        path.unlink()


def _ensure_users() -> dict[str, dict]:
    created: dict[str, dict] = {}
    for user in DEMO_USERS:
        existing = fetch_one("SELECT * FROM users WHERE email = ?", (user["email"],))
        if existing is None:
            created[user["email"]] = register_user(
                email=user["email"],
                password=user["password"],
                name=user["name"],
                role=user["role"],
                tenant_slug=DEFAULT_TENANT_SLUG,
                tenant_name="Default",
            )
        else:
            created[user["email"]] = existing
    return created


def _ensure_portfolio(name: str, user_id: str, initial_value: float) -> dict:
    portfolio = fetch_one("SELECT * FROM portfolios WHERE name = ?", (name,))
    if portfolio is not None:
        return portfolio
    now = datetime.now(timezone.utc).isoformat()
    portfolio_id = execute(
        """
        INSERT INTO portfolios (user_id, name, total_value, cash_balance, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, name, initial_value, initial_value, now, now),
    )
    return fetch_one("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,))


def _ensure_assets(portfolio_id: int) -> None:
    assets = (
        ("NVDA", "NVIDIA Corp.", 20, 845.0, 912.5, "stock", "Technology"),
        ("MSFT", "Microsoft Corp.", 24, 402.0, 418.0, "stock", "Technology"),
        ("JPM", "JPMorgan Chase", 32, 186.0, 193.0, "stock", "Finance"),
        ("GLD", "SPDR Gold Shares", 15, 211.0, 218.0, "etf", "Commodities"),
    )
    for symbol, name, quantity, purchase_price, current_price, asset_type, sector in assets:
        existing = fetch_one(
            "SELECT id FROM assets WHERE portfolio_id = ? AND symbol = ?",
            (portfolio_id, symbol),
        )
        if existing is not None:
            continue
        execute(
            """
            INSERT INTO assets (
                portfolio_id, symbol, name, quantity, purchase_price,
                current_price, asset_type, sector, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                portfolio_id,
                symbol,
                name,
                quantity,
                purchase_price,
                current_price,
                asset_type,
                sector,
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _risk_result(score: float, label: str, flags: list[str], *, reason: str) -> dict:
    return {
        "risk_score": score,
        "risk_label": label,
        "method": "seeded_demo",
        "hard_block": label == "critical",
        "flags": flags,
        "needs_llm_review": False,
        "rule_details": {"rule_score": score, "flags": flags, "details": {"reason": reason}},
        "ml_details": {
            "available": True,
            "ml_risk_score": score,
            "ml_risk_label": label,
            "ml_fraud_flag": label in {"high", "critical"},
            "ml_anomaly_score": round(score / 100.0, 2),
            "ml_confidence": 0.92,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _seed_transactions(portfolio: dict, tenant_id: int) -> dict:
    existing_case = fetch_one(
        "SELECT * FROM cases WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
        (portfolio["id"],),
    )
    if existing_case is not None:
        return existing_case

    base_time = datetime.now(timezone.utc) - timedelta(days=2)

    create_transaction_with_side_effects(
        portfolio,
        {
            "symbol": "MSFT",
            "type": "buy",
            "quantity": 5,
            "price": 410,
            "fees": 4.5,
            "notes": "Seeded baseline accumulation",
        },
        risk_result=_risk_result(
            18,
            "low",
            ["routine_volume"],
            reason="Baseline portfolio maintenance",
        ),
        now=base_time.isoformat(),
        tenant_id=tenant_id,
    )

    suspicious = create_transaction_with_side_effects(
        portfolio,
        {
            "symbol": "NVDA",
            "type": "sell",
            "quantity": 16,
            "price": 960,
            "fees": 15,
            "notes": "Seeded suspicious concentration unwind",
            "sender_country": "US",
            "receiver_country": "IR",
            "is_new_payee": 1,
            "failed_login_attempts_24h": 4,
            "num_txns_last_1h": 6,
            "num_txns_last_24h": 11,
            "amount_deviation_from_avg": 9.4,
            "portfolio_concentration_pct": 68,
            "is_high_risk_country": 1,
            "is_sanctioned_country": 1,
        },
        risk_result=_risk_result(
            91,
            "critical",
            [
                "sanctioned_country",
                "velocity_spike",
                "new_payee",
                "concentration_breach",
            ],
            reason="Synthetic suspicious-activity scenario for the case workflow demo",
        ),
        now=(base_time + timedelta(hours=8)).isoformat(),
        tenant_id=tenant_id,
    )

    case = suspicious.get("case")
    if case is None:
        raise RuntimeError("Demo seed expected an auto-opened case but none was created")

    ai_analysis = (
        "Seeded case analysis: critical transaction due to sanctions exposure, elevated transaction velocity, "
        "and concentrated liquidation behaviour. Recommended next step: supervisor review and SAR consideration."
    )
    with connect() as conn:
        conn.execute(
            """
            UPDATE cases
            SET ai_analysis = ?, updated_at = ?
            WHERE id = ?
            """,
            (ai_analysis, datetime.now(timezone.utc).isoformat(), case["id"]),
        )
        conn.execute(
            """
            INSERT INTO case_events (
                case_id, event_type, body, metadata, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                case["id"],
                "seed_note",
                "Supervisor review recommended. SAR export path is ready for demo.",
                json.dumps({"seeded": True}, ensure_ascii=True, sort_keys=True),
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    return fetch_one("SELECT * FROM cases WHERE id = ?", (case["id"],))


def seed_demo_data(reset: bool = False) -> dict:
    os.environ.setdefault("BACKEND_DB_PATH", _default_db_path())
    if reset:
        os.environ["DEMO_SEED"] = "reset"
    _reset_db_if_requested()
    init_db()

    users = _ensure_users()
    tenant = fetch_one("SELECT * FROM tenants WHERE slug = ?", (DEFAULT_TENANT_SLUG,))
    if tenant is None:
        raise RuntimeError("Default tenant missing after initialization")

    portfolio = _ensure_portfolio(
        "FinGuard Demo Portfolio",
        "customer_demo_001",
        250000.0,
    )
    _ensure_assets(int(portfolio["id"]))
    case = _seed_transactions(portfolio, int(tenant["id"]))

    return {
        "db_path": str(_db_path()),
        "tenant": {"id": tenant["id"], "slug": tenant["slug"]},
        "portfolio": {"id": portfolio["id"], "name": portfolio["name"]},
        "case": {"id": case["id"], "title": case["title"], "state": case["state"]},
        "users": [
            {
                "email": user["email"],
                "password": DEMO_USERS[index]["password"],
                "role": user["role"],
            }
            for index, user in enumerate(users.values())
        ],
        "notes": [
            "Use AUTH_ENFORCED=false for frictionless demos, or log in with the seeded users when auth is enforced.",
            "Set AI_RESPONSE_MODE=mock in ai_system/.env for deterministic offline demos and CI smoke checks.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed deterministic FinGuard demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the configured SQLite database before seeding.",
    )
    args = parser.parse_args()
    summary = seed_demo_data(reset=args.reset)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
