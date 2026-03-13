"""
decision_logger.py — The Brain's Memory
Every decision RCAgent-01 makes is logged here with full reasoning.
This is the most critical module: it proves the agent thinks autonomously.
"""

import os
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "rcagent.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------

class Decision(Base):
    """Every autonomous decision the agent makes."""
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    module = Column(String(64), nullable=False, index=True)
    action = Column(String(128), nullable=False)
    reasoning = Column(Text, nullable=False)
    outcome = Column(Text, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "module": self.module,
            "action": self.action,
            "reasoning": self.reasoning,
            "outcome": self.outcome,
        }

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)


def log_decision(module: str, action: str, reasoning: str, outcome: str) -> int:
    """
    Record a decision to the SQLite decisions table.

    Args:
        module:    Which module made the decision (e.g. 'content_engine').
        action:    Short verb phrase (e.g. 'chose_topic').
        reasoning: Full explanation of WHY this decision was made.
        outcome:   What happened as a result.

    Returns:
        The auto-generated decision ID.
    """
    session = SessionLocal()
    try:
        decision = Decision(
            module=module,
            action=action,
            reasoning=reasoning,
            outcome=outcome,
        )
        session.add(decision)
        session.commit()
        session.refresh(decision)
        return decision.id
    except Exception as exc:
        session.rollback()
        raise exc
    finally:
        session.close()


def get_all_decisions() -> list[dict]:
    """Return the complete decision history, newest first."""
    session = SessionLocal()
    try:
        rows = (
            session.query(Decision)
            .order_by(Decision.timestamp.desc())
            .all()
        )
        return [r.to_dict() for r in rows]
    finally:
        session.close()


def get_decisions_this_week() -> list[dict]:
    """Return decisions from the last 7 days, newest first."""
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        rows = (
            session.query(Decision)
            .filter(Decision.timestamp >= cutoff)
            .order_by(Decision.timestamp.desc())
            .all()
        )
        return [r.to_dict() for r in rows]
    finally:
        session.close()


def get_decisions_by_module(module: str) -> list[dict]:
    """Return all decisions for a specific module, newest first."""
    session = SessionLocal()
    try:
        rows = (
            session.query(Decision)
            .filter(Decision.module == module)
            .order_by(Decision.timestamp.desc())
            .all()
        )
        return [r.to_dict() for r in rows]
    finally:
        session.close()
