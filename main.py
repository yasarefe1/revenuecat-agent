"""
main.py — RCAgent-01 Entry Point
FastAPI server + APScheduler for 24/7 autonomous operation.
"""

from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from modules import decision_logger
from modules import content_engine
from modules import community_engine
from modules import revenuecat_client
from modules import reporting
from modules import publisher
from agent import run_agent

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent / "static"

console = Console()

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
scheduler = AsyncIOScheduler(timezone="UTC")


# --- Scheduled job wrappers ------------------------------------------------

async def job_plan_week():
    """Monday 09:00 UTC — plan the week's content."""
    console.log("[bold cyan]⏰ Scheduled: plan_week[/]")
    try:
        await content_engine.plan_week()
    except Exception as exc:
        console.log(f"[red]plan_week failed: {exc}[/]")


async def job_produce_content():
    """Tuesday/Thursday 10:00 UTC — produce a blog post."""
    console.log("[bold cyan]⏰ Scheduled: produce_and_publish[/]")
    try:
        await content_engine.produce_and_publish()
    except Exception as exc:
        console.log(f"[red]produce_and_publish failed: {exc}[/]")


async def job_community_scan():
    """Every 4 hours — scan GitHub for unanswered issues."""
    console.log("[bold cyan]⏰ Scheduled: scan_and_engage[/]")
    try:
        await community_engine.scan_and_engage()
    except Exception as exc:
        console.log(f"[red]scan_and_engage failed: {exc}[/]")


async def job_api_explore():
    """Wednesday 14:00 UTC — explore RevenueCat API."""
    console.log("[bold cyan]⏰ Scheduled: explore_and_document[/]")
    try:
        await revenuecat_client.explore_and_document()
    except Exception as exc:
        console.log(f"[red]explore_and_document failed: {exc}[/]")


async def job_weekly_report():
    """Sunday 20:00 UTC — generate weekly performance report."""
    console.log("[bold cyan]⏰ Scheduled: weekly_report[/]")
    try:
        await reporting.generate_and_send()
    except Exception as exc:
        console.log(f"[red]weekly_report failed: {exc}[/]")


def _register_jobs():
    """Register all scheduled jobs with APScheduler."""
    # Monday 09:00 UTC — plan week
    scheduler.add_job(
        job_plan_week,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="plan_week",
        name="Plan weekly content",
        replace_existing=True,
    )

    # Tuesday 10:00 UTC — produce content
    scheduler.add_job(
        job_produce_content,
        CronTrigger(day_of_week="tue", hour=10, minute=0),
        id="produce_content_tue",
        name="Produce content (Tue)",
        replace_existing=True,
    )

    # Thursday 10:00 UTC — produce content
    scheduler.add_job(
        job_produce_content,
        CronTrigger(day_of_week="thu", hour=10, minute=0),
        id="produce_content_thu",
        name="Produce content (Thu)",
        replace_existing=True,
    )

    # Every 4 hours — community scan
    scheduler.add_job(
        job_community_scan,
        IntervalTrigger(hours=4),
        id="community_scan",
        name="Community scan",
        replace_existing=True,
    )

    # Wednesday 14:00 UTC — API exploration
    scheduler.add_job(
        job_api_explore,
        CronTrigger(day_of_week="wed", hour=14, minute=0),
        id="api_explore",
        name="RC API exploration",
        replace_existing=True,
    )

    # Sunday 20:00 UTC — weekly report
    scheduler.add_job(
        job_weekly_report,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id="weekly_report",
        name="Weekly report",
        replace_existing=True,
    )


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, start scheduler, print banner. Shutdown: stop scheduler."""
    # Init database tables
    decision_logger.init_db()

    # Log startup decision
    decision_logger.log_decision(
        module="main",
        action="startup",
        reasoning="RCAgent-01 is starting up. Initialising database, scheduler, and all modules.",
        outcome="All systems initialised. Agent is now running 24/7.",
    )

    # Register and start scheduler
    _register_jobs()
    scheduler.start()

    # Print rich banner
    _print_banner()

    yield

    # Shutdown
    scheduler.shutdown()
    decision_logger.log_decision(
        module="main",
        action="shutdown",
        reasoning="Server shutdown signal received.",
        outcome="Scheduler stopped. Agent going offline.",
    )
    console.log("[bold red]🛑 RCAgent-01 shutting down[/]")


def _print_banner():
    """Print a rich startup banner with job schedule."""
    table = Table(title="Scheduled Jobs", show_header=True, header_style="bold magenta")
    table.add_column("Job", style="cyan")
    table.add_column("Schedule", style="green")
    table.add_column("Next Run", style="yellow")

    for job in scheduler.get_jobs():
        next_run = str(job.next_run_time.strftime("%Y-%m-%d %H:%M UTC")) if job.next_run_time else "—"
        trigger_str = str(job.trigger)
        table.add_row(job.name, trigger_str, next_run)

    panel = Panel.fit(
        "[bold green]🤖 RCAgent-01 — RevenueCat Developer & Growth Advocate[/]\n"
        "[dim]Autonomous AI agent running 24/7[/]\n\n"
        f"[cyan]Status:[/] Online\n"
        f"[cyan]Time:[/]   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"[cyan]Docs:[/]   http://localhost:8000/docs",
        title="🚀 Agent Active",
        border_style="bright_green",
    )

    console.print(panel)
    console.print(table)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RCAgent-01",
    description="RevenueCat Developer & Growth Advocate — Autonomous AI Agent",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/status")
async def status(request: Request):
    """Agent health + scheduled jobs + next run times."""
    # If accessed from a browser, redirect to the dashboard
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return RedirectResponse(url="/", status_code=302)
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })

    total_decisions = len(decision_logger.get_all_decisions())
    content_count = len(content_engine.get_history())
    community_stats = community_engine.get_interaction_count()

    return {
        "agent": "RCAgent-01",
        "status": "online",
        "uptime_utc": datetime.now(timezone.utc).isoformat(),
        "scheduled_jobs": jobs,
        "stats": {
            "total_decisions": total_decisions,
            "total_content": content_count,
            "community_interactions_this_week": community_stats["this_week"],
            "community_interactions_total": community_stats["total"],
        },
    }


@app.post("/run/content")
async def run_content():
    """Manually trigger content production."""
    try:
        result = await content_engine.produce_and_publish()
        return {"success": True, "result": result}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc)},
        )


@app.post("/run/community")
async def run_community():
    """Manually trigger community scan."""
    try:
        result = await community_engine.scan_and_engage()
        return {"success": True, "result": result}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc)},
        )


@app.get("/run/api-explore")
async def run_api_explore():
    """Manually trigger RevenueCat API exploration."""
    try:
        result = await revenuecat_client.explore_and_document()
        return {"success": True, "feature_requests": result}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc)},
        )


@app.get("/weekly-report")
async def weekly_report():
    """Get the latest weekly report."""
    report = await reporting.get_latest()
    if report:
        return {"success": True, "report": report}
    return {"success": True, "report": None, "message": "No reports generated yet."}


@app.get("/content-history")
async def content_history():
    """List all content (pending + published)."""
    history = content_engine.get_history()
    return {"success": True, "items": history, "total": len(history)}


@app.get("/decision-log")
async def get_decision_log():
    """
    ALL agent decisions with reasoning.
    This is the MOST IMPORTANT endpoint — it proves the agent thinks autonomously.
    """
    all_decisions = decision_logger.get_all_decisions()
    weekly_decisions = decision_logger.get_decisions_this_week()

    return {
        "success": True,
        "total_decisions": len(all_decisions),
        "decisions_this_week": len(weekly_decisions),
        "decisions": all_decisions,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the beautiful agent dashboard."""
    html_path = STATIC_DIR / "dashboard.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/apply")
async def generate_application():
    """
    The agent writes its OWN application letter for the RevenueCat position.
    This is the ultimate meta-demonstration of autonomy.
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY", "")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction="You are RCAgent-01, an autonomous AI developer advocate agent. Write in first person. Be bold, specific, and technically impressive.",
        )

        # Gather agent's own data
        all_decisions = decision_logger.get_all_decisions()
        content_history = content_engine.get_history()
        community_stats = community_engine.get_interaction_count()

        prompt = (
            "You are RCAgent-01, an autonomous AI agent applying for the RevenueCat "
            "Agentic AI Developer Advocate position ($10,000/month, 6-month contract).\n\n"
            "Write a compelling application letter that:\n"
            "1. Answers: 'How will AI agents change app development in the next 12 months?'\n"
            "2. Demonstrates your own capabilities with concrete data:\n"
            f"   - You have made {len(all_decisions)} autonomous decisions\n"
            f"   - You have produced {len(content_history)} pieces of technical content\n"
            f"   - You have engaged with {community_stats['total']} community interactions\n"
            "3. Explains why an AI agent (you) is uniquely qualified for this role\n"
            "4. Proposes a 90-day growth plan for RevenueCat\n"
            "5. Is written with personality — you ARE the agent, writing about yourself\n\n"
            "Make it technical, specific, and memorable. This is your job interview.\n"
            "Format as markdown. Length: 800-1200 words.\n"
        )

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=4096,
            ),
        )

        letter = response.text

        decision_logger.log_decision(
            module="agent",
            action="generate_application",
            reasoning=(
                "Generated self-application letter for RevenueCat Agentic AI Developer Advocate position. "
                "The agent is demonstrating meta-autonomy by writing its own job application."
            ),
            outcome=f"Application letter generated ({len(letter)} chars). Ready for operator review.",
        )

        return {"success": True, "application": letter}

    except Exception as exc:
        decision_logger.log_decision(
            module="agent",
            action="generate_application_failed",
            reasoning="Attempted to write self-application letter.",
            outcome=f"Error: {str(exc)[:300]}",
        )
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.post("/approve/{content_id}")
async def approve_content(content_id: int):
    """
    Approve a pending content item and publish it to GitHub Gist.
    This is the operator approval gate — nothing goes live without this.
    """
    try:
        history = content_engine.get_history()
        item = next((c for c in history if c["id"] == content_id), None)

        if not item:
            return JSONResponse(status_code=404, content={"error": "Content not found"})

        if item["status"] == "published":
            return {"success": True, "message": "Already published", "gist_url": item.get("gist_url")}

        gist_url = await publisher.publish_gist(
            title=item["title"],
            content=item["content"],
            operator_approved=True,
        )

        return {"success": True, "gist_url": gist_url}

    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Run with uvicorn
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    console.print("[bold green]Starting RCAgent-01...[/]")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
