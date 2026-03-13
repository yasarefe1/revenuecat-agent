"""
publisher.py — GitHub Gist Publisher
Publishes operator-approved content to GitHub Gists.
IMPORTANT: Never publishes without operator_approved=True.
"""

import os
from datetime import datetime, timezone

from github import Github, GithubException, InputFileContent
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

from modules import decision_logger

# ---------------------------------------------------------------------------
# Database (reuses the same SQLite file)
# ---------------------------------------------------------------------------
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database")
DB_PATH = os.path.join(DB_DIR, "rcagent.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class PublishedGist(Base):
    """Record of every published GitHub Gist."""
    __tablename__ = "published_gists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    gist_url = Column(String(512), nullable=False)
    content_preview = Column(Text, nullable=True)
    published_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "gist_url": self.gist_url,
            "content_preview": self.content_preview[:200] if self.content_preview else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }


def _init_publisher_table():
    Base.metadata.create_all(bind=engine)


_init_publisher_table()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def publish_gist(
    title: str,
    content: str,
    operator_approved: bool = False,
) -> str:
    """
    Publish content as a public GitHub Gist.

    Args:
        title:              Title of the post (used as filename).
        content:            Full markdown content.
        operator_approved:  MUST be True or publication is refused.

    Returns:
        The URL of the created Gist.

    Raises:
        PermissionError: If operator_approved is False.
        GithubException:  If GitHub API call fails.
    """
    if not operator_approved:
        decision_logger.log_decision(
            module="publisher",
            action="publish_gist_blocked",
            reasoning=f"Attempted to publish '{title}' but operator_approved=False.",
            outcome="BLOCKED — operator approval is required before any content goes live.",
        )
        raise PermissionError(
            "Operator approval required before publishing. "
            "Set operator_approved=True after manual review."
        )

    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        decision_logger.log_decision(
            module="publisher",
            action="publish_gist_no_token",
            reasoning=f"Tried to publish '{title}' but GITHUB_TOKEN is not set.",
            outcome="FAILED — missing GitHub token in environment.",
        )
        raise EnvironmentError("GITHUB_TOKEN is not configured in .env")

    try:
        gh = Github(github_token)
        user = gh.get_user()

        # Sanitise title for filename
        safe_name = title.lower().replace(" ", "-").replace(":", "")[:80] + ".md"

        gist = user.create_gist(
            public=True,
            files={safe_name: InputFileContent(content)},
            description=f"RCAgent-01 | {title}",
        )

        gist_url = gist.html_url

        # Persist to SQLite
        session = SessionLocal()
        try:
            record = PublishedGist(
                title=title,
                gist_url=gist_url,
                content_preview=content[:500],
            )
            session.add(record)
            session.commit()
        finally:
            session.close()

        decision_logger.log_decision(
            module="publisher",
            action="publish_gist_success",
            reasoning=(
                f"Operator approved publication of '{title}'. "
                f"Created public Gist under user '{user.login}'."
            ),
            outcome=f"Published successfully: {gist_url}",
        )

        return gist_url

    except GithubException as exc:
        decision_logger.log_decision(
            module="publisher",
            action="publish_gist_github_error",
            reasoning=f"Attempted to publish '{title}' to GitHub Gist.",
            outcome=f"GitHub API error: {str(exc)[:300]}",
        )
        raise
    except Exception as exc:
        decision_logger.log_decision(
            module="publisher",
            action="publish_gist_error",
            reasoning=f"Attempted to publish '{title}' to GitHub Gist.",
            outcome=f"Unexpected error: {str(exc)[:300]}",
        )
        raise


def list_published() -> list[dict]:
    """Return all published gists from SQLite, newest first."""
    session = SessionLocal()
    try:
        rows = (
            session.query(PublishedGist)
            .order_by(PublishedGist.published_at.desc())
            .all()
        )
        return [r.to_dict() for r in rows]
    finally:
        session.close()
