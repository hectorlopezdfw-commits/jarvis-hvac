from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import String, Text, create_engine, desc, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.db.seed import seed_leads


class Base(DeclarativeBase):
    pass


class LeadRow(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class FirstRingSignupRow(Base):
    """FirstRing marketing-site sign-ups. Same engine and create_all path as leads."""

    __tablename__ = "firstring_signups"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_database_url(raw: str | None) -> str:
    """Accept DATABASE_URL, with a local SQLite file when it is unset.

    Render Postgres URLs use the postgres:// scheme. SQLAlchemy talks to that
    database through the psycopg v3 driver, so the scheme is rewritten here.
    """
    value = (raw or "").strip()
    if not value:
        path = project_root() / "data" / "jarvis.db"
        value = "sqlite:///" + path.as_posix()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://") :]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://") :]
    if value.startswith("sqlite"):
        value = _absolutize_sqlite_url(value)
    return value


def _absolutize_sqlite_url(url: str) -> str:
    prefix = "sqlite:///"
    path_part = url[len(prefix) :]
    if path_part.startswith(":memory:"):
        return url
    path = Path(path_part)
    if not path.is_absolute():
        path = project_root() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return prefix + path.as_posix()


def _create_engine(url: str):
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
        if ":memory:" in url:
            return create_engine(url, connect_args=connect_args, poolclass=StaticPool)
        return create_engine(url, connect_args=connect_args, poolclass=NullPool)
    return create_engine(url, pool_pre_ping=True)


class SqlLeadStore:
    """Lead store with the same create/list/get/update behavior as the old in-memory store."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = resolve_database_url(database_url)
        self._engine = _create_engine(self.database_url)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        Base.metadata.create_all(self._engine)
        seed_leads(self)

    def dispose(self) -> None:
        self._engine.dispose()

    def _session(self) -> Session:
        return self._session_factory()

    def create(self, lead: dict[str, Any]) -> dict[str, Any]:
        lead = dict(lead)
        with self._session() as session:
            supplied_id = lead.get("id")
            if supplied_id:
                existing = session.get(LeadRow, supplied_id)
                if existing is not None:
                    return json.loads(existing.payload)
            else:
                lead["id"] = self._next_lead_id(session)

            if "created_at" not in lead:
                lead["created_at"] = datetime.now(timezone.utc).isoformat()
            if "status" not in lead:
                lead["status"] = "new"
            if "priority_score" not in lead:
                lead["priority_score"] = 0
            if "priority_label" not in lead:
                lead["priority_label"] = "medium"

            row = LeadRow(
                id=str(lead["id"]),
                created_at=str(lead.get("created_at") or ""),
                payload=json.dumps(lead),
            )
            session.add(row)
            session.commit()
            return json.loads(row.payload)

    def list(self) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(select(LeadRow).order_by(LeadRow.created_at, LeadRow.id)).all()
            return [json.loads(row.payload) for row in rows]

    def get(self, lead_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            row = session.get(LeadRow, lead_id)
            return json.loads(row.payload) if row else None

    def update(self, lead_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(LeadRow, lead_id)
            if row is None:
                raise KeyError(f"Lead {lead_id} not found")
            lead = json.loads(row.payload)
            lead.update(updates)
            row.payload = json.dumps(lead)
            if "created_at" in lead:
                row.created_at = str(lead["created_at"])
            session.commit()
            return json.loads(row.payload)

    def create_signup(self, signup: dict[str, Any]) -> dict[str, Any]:
        signup = dict(signup)
        with self._session() as session:
            if not signup.get("id"):
                signup["id"] = self._next_signup_id(session)
            if "created_at" not in signup:
                signup["created_at"] = datetime.now(timezone.utc).isoformat()
            row = FirstRingSignupRow(
                id=str(signup["id"]),
                created_at=str(signup.get("created_at") or ""),
                payload=json.dumps(signup),
            )
            session.add(row)
            session.commit()
            return json.loads(row.payload)

    def list_signups(self) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(
                select(FirstRingSignupRow).order_by(desc(FirstRingSignupRow.created_at), desc(FirstRingSignupRow.id))
            ).all()
            return [json.loads(row.payload) for row in rows]

    def get_signup(self, signup_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            row = session.get(FirstRingSignupRow, signup_id)
            return json.loads(row.payload) if row else None

    def update_signup(self, signup_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(FirstRingSignupRow, signup_id)
            if row is None:
                raise KeyError(f"Signup {signup_id} not found")
            signup = json.loads(row.payload)
            signup.update(updates)
            row.payload = json.dumps(signup)
            if "created_at" in signup:
                row.created_at = str(signup["created_at"])
            session.commit()
            return json.loads(row.payload)

    def _next_signup_id(self, session: Session) -> str:
        count = session.scalar(select(func.count()).select_from(FirstRingSignupRow)) or 0
        number = int(count) + 1
        signup_id = f"signup-{number:04d}"
        while session.get(FirstRingSignupRow, signup_id) is not None:
            number += 1
            signup_id = f"signup-{number:04d}"
        return signup_id

    def _next_lead_id(self, session: Session) -> str:
        count = session.scalar(select(func.count()).select_from(LeadRow)) or 0
        number = int(count) + 1
        lead_id = f"lead-{number:04d}"
        while session.get(LeadRow, lead_id) is not None:
            number += 1
            lead_id = f"lead-{number:04d}"
        return lead_id


def _default_database_url() -> str:
    from app.config import settings

    return settings.database_url


lead_store = SqlLeadStore(_default_database_url())
