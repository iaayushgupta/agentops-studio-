# CLAUDE.md — Project Context

## Project
Yuno AI Engineer Challenge: AI Agent Orchestration Platform
Submission deadline: 29 May 2026

## Stack
- Backend: FastAPI + Python 3.11
- Runtime: LangGraph 0.2.x + LangChain
- Database: PostgreSQL 16 only (no SQLite, no Redis)
- Realtime: FastAPI native WebSocket
- Messaging: python-telegram-bot v20 (async polling, no webhook)
- Frontend: Next.js 14 + TypeScript + Tailwind + shadcn/ui + @xyflow/react
- LLM Primary: Google Gemini 1.5 Flash via langchain-google-genai (free)
- LLM Fallback: Groq llama-3.3-70b-versatile via langchain-groq (free)
- Both providers are free — no Anthropic, no OpenAI
- Infra: Docker Compose (3 services: postgres, backend, frontend)

## LLM Provider Config Pattern
Use a get_llm(provider, model) factory function in app/runtime/llm.py.
Provider switching via DEFAULT_MODEL_PROVIDER env var (google | groq | ollama).
All agents use this factory — never import provider SDK directly in agent code.

## Architecture Rules
1. Clean separation: API layer → Service layer → Runtime layer → DB
2. WorkflowCompiler is the critical class: converts JSON DAG → LangGraph StateGraph
3. LangGraph PostgresSaver handles runtime checkpoints; domain tables handle product data
4. No Celery, no Redis, no APScheduler — explicitly deferred with production notes
5. Telegram polling runs as asyncio background task inside backend container
6. workflow.graph_json stores full React Flow DAG (no separate nodes/edges tables)

## Database Tables (7)
agents, workflows, runs, run_steps, messages, tool_calls, token_usage

## Mock Data Tables (in same Postgres DB — no SQLite)
mock_transactions, mock_psp_status, mock_routing_logs

## Demo Scenario
Payment Failure Triage:
Telegram → Intake Agent → Investigator Agent → Condition (failure_type)
→ Resolution Agent OR Escalation Agent → Reviewer Agent
→ Condition (reviewer_score >= 7) → Telegram Response
(one reviewer retry max, then force end)

## Tools (all backed by Postgres mock tables)
get_transaction, get_psp_status, check_routing_logs,
suggest_alternate_psp, send_telegram_message, calculator

## Key Design Decisions for README
- LangGraph: state-machine maps to visual DAG with conditions/loops; PostgresSaver = free checkpoint persistence
- Telegram: polling works locally, no public URL needed, 60s setup
- No Redis/Celery: FastAPI background tasks + asyncio sufficient at this scope
- graph_json over normalized nodes/edges tables: MVP speed; production can normalize
- Gemini Flash + Groq: both free, both support tool calling via LangChain bind_tools()
- Single Postgres DB for domain data AND mock payment data — no dual persistence

## Deliberate Cuts (must mention in README)
- Cron scheduler (config field + UI exists; execution deferred)
- Auth/multi-tenancy (single user; production: Clerk + tenant_id FK)
- WhatsApp/Slack (ChannelAdapter ABC defined; Telegram implemented)
- Workflow versioning (latest version only)
- Multi-provider LLM (factory supports google|groq|ollama; Gemini primary)