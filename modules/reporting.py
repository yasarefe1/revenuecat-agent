"""
reporting.py — Weekly Performance Reports
Generates a comprehensive markdown report every Sunday at 20:00 UTC.
Aggregates data from all modules and uses Gemini for narrative synthesis.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import google.generativeai as genai
from sqlalchemy import create_engine, Column, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

from modules import decision_logger
from modules import content_engine
from modules import community_engine
from modules import publisher

# ---------------------------------------------------------------------------
# Database (reuses the same SQLite file)
# ---------------------------------------------------------------------------
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database")
DB_PATH = os.path.join(DB_DIR, "rcagent.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class WeeklyReport(Base):
    """Stored weekly performance reports."""
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_markdown = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "report_markdown": self.report_markdown,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }


def _init_report_table():
    Base.metadata.create_all(bind=engine)


_init_report_table()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_report_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "report.txt"
    return prompt_path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_and_send() -> str:
    """
    Generate a detailed weekly performance report.

    Pulls data from:
    - content_engine  → content produced
    - community_engine → interaction counts
    - publisher        → gists published
    - decision_logger  → decision log for the week

    Returns:
        Markdown string of the report.
    """
    # --- Gather data -------------------------------------------------------
    content_history = content_engine.get_history()
    community_stats = community_engine.get_interaction_count()
    published_gists = publisher.list_published()
    weekly_decisions = decision_logger.get_decisions_this_week()

    # --- Build data summary for Gemini ------------------------------------
    data_summary = (
        "# Raw Data for Report Generation\n\n"
        f"## Content Produced\n"
        f"Total items: {len(content_history)}\n"
    )
    for item in content_history[:10]:
        status = item.get("status", "unknown")
        title = item.get("title", "Untitled")
        data_summary += f"- [{status}] {title}\n"

    data_summary += (
        f"\n## Community Interactions\n"
        f"This week: {community_stats['this_week']}\n"
        f"Total: {community_stats['total']}\n"
    )

    data_summary += (
        f"\n## Published Gists\n"
        f"Total: {len(published_gists)}\n"
    )
    for gist in published_gists[:10]:
        data_summary += f"- {gist['title']}: {gist['gist_url']}\n"

    data_summary += (
        f"\n## Decision Log (This Week)\n"
        f"Total decisions: {len(weekly_decisions)}\n\n"
    )
    for dec in weekly_decisions[:30]:
        data_summary += (
            f"### [{dec['module']}] {dec['action']}\n"
            f"**Reasoning:** {dec['reasoning']}\n"
            f"**Outcome:** {dec['outcome']}\n"
            f"**Time:** {dec['timestamp']}\n\n"
        )

    # --- Generate report via Gemini ----------------------------------------
    system_prompt = _load_report_prompt()

    user_prompt = (
        "Generate a weekly performance report for RCAgent-01 using the following data.\n"
        "Structure the report with these sections:\n"
        "1. Content produced (titles + links)\n"
        "2. Community interactions (count by platform)\n"
        "3. RevenueCat API findings\n"
        "4. Feature requests drafted\n"
        "5. DECISION LOG: every decision + reasoning this week\n"
        "6. Next week plan\n\n"
        f"{data_summary}"
    )

    try:
        api_key = os.getenv("GEMINI_API_KEY", "")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=system_prompt,
        )

        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=4096,
            ),
        )

        report_md = response.text

        # Persist
        session = SessionLocal()
        try:
            report = WeeklyReport(report_markdown=report_md)
            session.add(report)
            session.commit()
        finally:
            session.close()

        decision_logger.log_decision(
            module="reporting",
            action="generate_weekly_report",
            reasoning=(
                f"Generated weekly report covering {len(content_history)} content items, "
                f"{community_stats['this_week']} community interactions, "
                f"and {len(weekly_decisions)} decisions this week."
            ),
            outcome=f"Report generated ({len(report_md)} chars) and saved to database.",
        )

        return report_md

    except Exception as exc:
        decision_logger.log_decision(
            module="reporting",
            action="generate_weekly_report_failed",
            reasoning="Attempted to generate weekly performance report via Gemini API.",
            outcome=f"Error: {str(exc)[:300]}",
        )
        raise


async def get_latest() -> str | None:
    """Return the most recent weekly report from SQLite, or None."""
    session = SessionLocal()
    try:
        report = (
            session.query(WeeklyReport)
            .order_by(WeeklyReport.generated_at.desc())
            .first()
        )
        return report.report_markdown if report else None
    finally:
        session.close()
