from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (JSON, CheckConstraint, Date, DateTime, ForeignKey, Integer, LargeBinary,
                        String, Text, UniqueConstraint, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (CheckConstraint('free_credits >= 0'), CheckConstraint('paid_credits >= 0'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200))
    free_credits: Mapped[int] = mapped_column(Integer, default=100)
    paid_credits: Mapped[int] = mapped_column(Integer, default=0)
    reset_date: Mapped[object] = mapped_column(Date)


class PasswordCredential(Base):
    __tablename__ = 'password_credentials'
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), unique=True)
    salt: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(128))


class Login(Base):
    __tablename__ = 'logins'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Source(Base):
    __tablename__ = 'sources'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text)
    filename: Mapped[str | None] = mapped_column(String(255))
    original: Mapped[bytes | None] = mapped_column(LargeBinary)
    graph: Mapped[dict] = mapped_column(JSON)
    extraction: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Question(Base):
    __tablename__ = 'questions'
    __table_args__ = (UniqueConstraint('source_id', 'fact_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey('sources.id'), index=True)
    fact_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(10))
    prompt: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Operation(Base):
    __tablename__ = 'operations'
    __table_args__ = (UniqueConstraint('user_id', 'key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    key: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)


class Ledger(Base):
    __tablename__ = 'ledger'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


is_sqlite = settings.database_url.startswith('sqlite')
engine = create_engine(settings.database_url, pool_pre_ping=True,
                       connect_args={'check_same_thread': False, 'timeout': 120} if is_sqlite else {})
if is_sqlite:
    @event.listens_for(engine, 'connect')
    def sqlite_settings(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')

Session = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction():
    with Session() as db:
        try:
            # SQLite lacks row locks; serialize local writes. Postgres uses user row locks.
            if is_sqlite:
                db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
