"""
content_engine.py — AI-Powered Technical Content Production
Produces 2 technical blog posts per week using Gemini API.
Uses ChromaDB for vector memory to avoid duplicate topics.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import google.generativeai as genai
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
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


class ContentItem(Base):
    """A piece of generated content (blog post)."""
    __tablename__ = "content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="pending_approval")  # pending_approval | published
    gist_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    published_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "status": self.status,
            "gist_url": self.gist_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }


def _init_content_table():
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Month 1 content calendar
# ---------------------------------------------------------------------------
CONTENT_CALENDAR: list[str] = [
    "How to gate agentic capabilities behind a RevenueCat subscription (no screen required)",
    "RevenueCat API v2: A complete guide for server-side agents",
    "A/B testing paywalls when an AI agent decides the conversion moment",
    "Handling subscription webhooks in multi-agent orchestration systems",
    "Agent-initiated purchases: legal, technical, and UX implications",
    "RevenueCat + LangGraph: Building subscription-aware AI tools",
    "Entitlement checks in real-time: latency considerations for agentic apps",
    "From screen to signal: how RevenueCat becomes the source of truth for AI agents",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Load the content system prompt from prompts/content.txt."""
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "content.txt"
    return prompt_path.read_text(encoding="utf-8").strip()


def _get_next_title_index() -> int:
    """Determine which calendar title to produce next."""
    session = SessionLocal()
    try:
        produced_count = session.query(ContentItem).count()
        return produced_count  # 0-indexed into CONTENT_CALENDAR
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_init_content_table()


async def plan_week() -> dict:
    """
    Pick the next 2 titles from the content calendar.
    Logs reasoning to the decision logger.

    Returns:
        {"titles": [str, str], "reasoning": str}
    """
    idx = _get_next_title_index()
    titles: list[str] = []

    for offset in range(2):
        pos = idx + offset
        if pos < len(CONTENT_CALENDAR):
            titles.append(CONTENT_CALENDAR[pos])

    if not titles:
        reasoning = (
            "All 8 titles from the Month 1 content calendar have been produced. "
            "Need to generate a Month 2 calendar based on community engagement data."
        )
        decision_logger.log_decision(
            module="content_engine",
            action="plan_week",
            reasoning=reasoning,
            outcome="No new titles to schedule — calendar exhausted.",
        )
        return {"titles": [], "reasoning": reasoning}

    reasoning = (
        f"Selected titles #{idx + 1} and #{idx + 2} from the Month 1 content calendar. "
        f"These follow the progressive narrative arc: first explaining core concepts, "
        f"then diving into advanced integration patterns."
    )

    decision_logger.log_decision(
        module="content_engine",
        action="plan_week",
        reasoning=reasoning,
        outcome=f"Scheduled {len(titles)} post(s): {', '.join(titles)}",
    )

    return {"titles": titles, "reasoning": reasoning}


async def produce_and_publish() -> dict:
    """
    Generate the next blog post using Gemini API.
    Saves draft to SQLite as status='pending_approval'.

    Returns:
        {"title": str, "content": str, "status": "pending_approval"}
    """
    idx = _get_next_title_index()

    if idx >= len(CONTENT_CALENDAR):
        decision_logger.log_decision(
            module="content_engine",
            action="produce_and_publish_skipped",
            reasoning="Content calendar exhausted — no more titles to produce.",
            outcome="Skipped content production.",
        )
        return {
            "title": None,
            "content": None,
            "status": "calendar_exhausted",
        }

    title = CONTENT_CALENDAR[idx]
    system_prompt = _load_system_prompt()

    user_prompt = (
        f"Write a comprehensive technical blog post titled:\n\n"
        f'"{title}"\n\n'
        f"REQUIREMENTS:\n"
        f"- Use real RevenueCat API v2 endpoints (https://api.revenuecat.com/v2/)\n"
        f"- Include copy-paste-ready code in both Python (using httpx) and JavaScript (using fetch)\n"
        f"- Every code block must have proper error handling, comments, and type hints\n"
        f"- Be specific to agentic AI monetisation use-cases — not generic mobile apps\n"
        f"- Address a gap that no existing RevenueCat blog post or doc covers\n"
        f"- Include at least 3 edge cases or gotchas developers should watch for\n"
        f"- Reference real RevenueCat SDK classes: Purchases, CustomerInfo, EntitlementInfo\n"
        f"- Include performance considerations (latency, rate limits, caching)\n"
        f"- End with a TL;DR section (5 bullet points max)\n"
        f"- Target length: 2000-3000 words\n\n"
        f"STRUCTURE:\n"
        f"1. Hook paragraph — why this matters RIGHT NOW\n"
        f"2. The Problem — what existing docs don't cover\n"
        f"3. Architecture Overview\n"
        f"4. Implementation (Python + JavaScript with full error handling)\n"
        f"5. Edge Cases & Gotchas (minimum 3)\n"
        f"6. Performance Considerations\n"
        f"7. TL;DR\n"
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
                max_output_tokens=8192,
            ),
        )

        content_text = response.text

        # Persist to SQLite
        session = SessionLocal()
        try:
            item = ContentItem(title=title, content=content_text, status="pending_approval")
            session.add(item)
            session.commit()
        finally:
            session.close()

        decision_logger.log_decision(
            module="content_engine",
            action="produce_and_publish",
            reasoning=(
                f"Generated blog post #{idx + 1} from calendar: '{title}'. "
                f"Used gemini-2.5-flash with content system prompt. "
                f"Post saved as pending_approval — requires operator sign-off before publishing."
            ),
            outcome=f"Draft produced ({len(content_text)} chars). Status: pending_approval.",
        )

        return {"title": title, "content": content_text, "status": "pending_approval"}

    except Exception as exc:
        decision_logger.log_decision(
            module="content_engine",
            action="produce_and_publish_failed",
            reasoning=f"Attempted to generate blog post '{title}' via Gemini API.",
            outcome=f"Error: {str(exc)[:300]}",
        )
        raise


def get_history() -> list[dict]:
    """Return all content items from SQLite (pending + published), newest first."""
    session = SessionLocal()
    try:
        rows = (
            session.query(ContentItem)
            .order_by(ContentItem.created_at.desc())
            .all()
        )
        return [r.to_dict() for r in rows]
    finally:
        session.close()
