"""
community_engine.py — Developer Community Engagement
Scans RevenueCat GitHub repos for unanswered issues every 4 hours.
Generates draft replies using Gemini API, pending operator approval.
"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import google.generativeai as genai
from github import Github, GithubException
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
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


class CommunityInteraction(Base):
    """Record of every drafted or posted community reply."""
    __tablename__ = "community_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo = Column(String(128), nullable=False)
    issue_number = Column(Integer, nullable=False)
    issue_title = Column(String(512), nullable=False)
    issue_url = Column(String(512), nullable=False)
    draft_reply = Column(Text, nullable=False)
    status = Column(String(32), default="pending_approval")  # pending_approval | posted
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    posted_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "repo": self.repo,
            "issue_number": self.issue_number,
            "issue_title": self.issue_title,
            "issue_url": self.issue_url,
            "draft_reply": self.draft_reply,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
        }


def _init_community_table():
    Base.metadata.create_all(bind=engine)


_init_community_table()

# ---------------------------------------------------------------------------
# Target repos
# ---------------------------------------------------------------------------
TARGET_REPOS: list[str] = [
    "RevenueCat/purchases-ios",
    "RevenueCat/purchases-android",
    "RevenueCat/purchases-flutter",
    "RevenueCat/purchases-react-native",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_community_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "community.txt"
    return prompt_path.read_text(encoding="utf-8").strip()


def _already_replied(repo: str, issue_number: int) -> bool:
    """Check if we already have a draft/posted reply for this issue."""
    session = SessionLocal()
    try:
        count = (
            session.query(CommunityInteraction)
            .filter(
                CommunityInteraction.repo == repo,
                CommunityInteraction.issue_number == issue_number,
            )
            .count()
        )
        return count > 0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def scan_and_engage() -> dict:
    """
    Scan target GitHub repos for unanswered issues.
    For each, generate a Gemini-powered draft reply (pending approval).

    Returns:
        {"scanned": int, "replies_drafted": int}
    """
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        decision_logger.log_decision(
            module="community_engine",
            action="scan_skipped",
            reasoning="GITHUB_TOKEN not set — cannot access GitHub API.",
            outcome="Scan skipped entirely.",
        )
        return {"scanned": 0, "replies_drafted": 0}

    gh = Github(github_token)
    system_prompt = _load_community_prompt()
    api_key = os.getenv("GEMINI_API_KEY", "")

    total_scanned = 0
    total_drafted = 0

    for repo_name in TARGET_REPOS:
        try:
            repo = gh.get_repo(repo_name)
            # Fetch recent open issues (last 30 days, max 10 per repo)
            since = datetime.now(timezone.utc) - timedelta(days=30)
            issues = repo.get_issues(state="open", sort="created", direction="desc", since=since)

            issue_count = 0
            for issue in issues:
                if issue_count >= 10:
                    break

                # Skip pull requests
                if issue.pull_request is not None:
                    continue

                total_scanned += 1
                issue_count += 1

                # Skip if we already generated a reply
                if _already_replied(repo_name, issue.number):
                    continue

                # Skip issues that already have maintainer replies
                comments = issue.get_comments()
                has_reply = any(
                    c.user and c.user.login != issue.user.login
                    for c in comments
                )
                if has_reply:
                    continue

                # Generate draft reply with Gemini
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(
                        "gemini-2.5-flash",
                        system_instruction=system_prompt,
                    )

                    user_content = (
                        f"Repository: {repo_name}\n"
                        f"Issue #{issue.number}: {issue.title}\n\n"
                        f"Issue body:\n{(issue.body or 'No description provided.')[:2000]}\n"
                    )

                    response = model.generate_content(
                        user_content,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=2048,
                        ),
                    )

                    draft = response.text

                    # Save to SQLite
                    session = SessionLocal()
                    try:
                        interaction = CommunityInteraction(
                            repo=repo_name,
                            issue_number=issue.number,
                            issue_title=issue.title,
                            issue_url=issue.html_url,
                            draft_reply=draft,
                            status="pending_approval",
                        )
                        session.add(interaction)
                        session.commit()
                    finally:
                        session.close()

                    total_drafted += 1

                    decision_logger.log_decision(
                        module="community_engine",
                        action="draft_reply",
                        reasoning=(
                            f"Found unanswered issue in {repo_name}: "
                            f"#{issue.number} '{issue.title}'. "
                            f"No maintainer response detected. "
                            f"Generated technical reply with gemini-2.5-flash."
                        ),
                        outcome=f"Draft reply saved ({len(draft)} chars). Status: pending_approval.",
                    )

                except Exception as exc:
                    decision_logger.log_decision(
                        module="community_engine",
                        action="draft_reply_failed",
                        reasoning=f"Failed to generate reply for {repo_name}#{issue.number}.",
                        outcome=f"Error: {str(exc)[:300]}",
                    )

        except GithubException as exc:
            decision_logger.log_decision(
                module="community_engine",
                action="repo_scan_failed",
                reasoning=f"Failed to scan repository {repo_name}.",
                outcome=f"GitHub error: {str(exc)[:300]}",
            )
        except Exception as exc:
            decision_logger.log_decision(
                module="community_engine",
                action="repo_scan_error",
                reasoning=f"Unexpected error scanning {repo_name}.",
                outcome=f"Error: {str(exc)[:300]}",
            )

    decision_logger.log_decision(
        module="community_engine",
        action="scan_and_engage_complete",
        reasoning=(
            f"Completed community scan across {len(TARGET_REPOS)} repos. "
            f"Scanned {total_scanned} issues, drafted {total_drafted} new replies."
        ),
        outcome=f"Scanned: {total_scanned}, Drafted: {total_drafted}.",
    )

    return {"scanned": total_scanned, "replies_drafted": total_drafted}


def get_interaction_count() -> dict:
    """
    Return interaction counts.

    Returns:
        {"this_week": int, "total": int}
    """
    session = SessionLocal()
    try:
        total = session.query(CommunityInteraction).count()
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        this_week = (
            session.query(CommunityInteraction)
            .filter(CommunityInteraction.created_at >= cutoff)
            .count()
        )
        return {"this_week": this_week, "total": total}
    finally:
        session.close()
