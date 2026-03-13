# 🤖 RCAgent-01 — RevenueCat Developer & Growth Advocate

An autonomous AI agent that runs 24/7 — producing technical content about RevenueCat, engaging with developer communities, exploring the RevenueCat API, and logging every decision it makes with full reasoning.

## ⚡ Quick Setup

```bash
# 1. Install Python 3.13 from python.org (check "Add to PATH")

# 2. Install dependencies
cd revenuecat-agent
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env with your API keys (minimum: ANTHROPIC_API_KEY + GITHUB_TOKEN)

# 4. Run
python main.py
```

The server starts at **http://localhost:8000** — a **live dashboard** opens at the root URL.

## 🧪 Test It

```bash
# Open the dashboard
http://localhost:8000

# Generate your first blog post
curl -X POST http://localhost:8000/run/content

# Agent writes its OWN job application
curl -X POST http://localhost:8000/apply

# See every decision the agent has made
curl http://localhost:8000/decision-log
```

## 🔑 Key Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | 🎨 **Live dashboard** with stats, actions, decision log |
| `/status` | GET | Agent health, scheduled jobs, next run times |
| `/run/content` | POST | Manually trigger content production |
| `/run/community` | POST | Manually trigger community scan |
| `/run/api-explore` | GET | Trigger RevenueCat API exploration |
| `/apply` | POST | Agent writes its own application letter |
| `/approve/{id}` | POST | Approve & publish content to GitHub Gist |
| `/weekly-report` | GET | Get latest weekly performance report |
| `/content-history` | GET | List all content (pending + published) |
| **`/decision-log`** | **GET** | **ALL agent decisions with reasoning** ← Most important |

## 📅 Automated Schedule (UTC)

| Day | Time | Job |
|---|---|---|
| Monday | 09:00 | Plan week's content |
| Tuesday | 10:00 | Produce blog post #1 |
| Thursday | 10:00 | Produce blog post #2 |
| Every 4h | — | Community issue scan |
| Wednesday | 14:00 | RevenueCat API exploration |
| Sunday | 20:00 | Weekly performance report |

## 🚀 Deploy to Railway

1. Push this repo to GitHub
2. Connect to [Railway](https://railway.app)
3. Add environment variables from `.env.example`
4. Deploy — the agent starts automatically

## 🧱 Architecture

```
main.py                → FastAPI + APScheduler + Dashboard (entry point)
agent.py               → LangGraph ReAct orchestration (11 tools)
static/
  dashboard.html       → Live dark-theme web dashboard
modules/
  decision_logger.py   → SQLite decision audit trail (MOST CRITICAL)
  content_engine.py    → Claude-powered blog post generation
  revenuecat_client.py → RevenueCat REST API v1/v2
  community_engine.py  → GitHub issue scanning + draft replies
  publisher.py         → GitHub Gist publishing (requires approval)
  reporting.py         → Weekly performance reports
```

## 🛡️ Safety Rules

- **Nothing is published** without `operator_approved=True`
- Every Claude call uses `claude-sonnet-4-20250514`
- All API keys loaded from `.env` — never hardcoded
- Every decision is logged to SQLite with full reasoning
