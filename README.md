# AgentOps Studio

Visual multi-agent orchestration platform — configure agents, build async workflows, execute real tools, monitor inter-agent communication, interact via Telegram.

---

## Who Is This For

**Operations teams** use AgentOps Studio to automate repetitive
workflows — payment triage, fraud alerts, support escalation —
without writing code.

**Non-technical operators** configure agents, build workflows
visually, and manage routing rules entirely from the browser.
No developer involvement after initial setup.

**Technical teams** use the platform to deploy agent infrastructure
that their ops teams can own and iterate on independently.

---

## 1. Quick Start

**Prerequisites:** Docker Desktop, a free [Google AI Studio](https://aistudio.google.com) key, a free [Groq](https://console.groq.com) key, and optionally a Telegram bot token from [@BotFather](https://t.me/botfather).

```bash
git clone https://github.com/your-org/yuno-agent-platform
cd yuno-agent-platform

cp .env.example .env
# Edit .env — add GOOGLE_API_KEY, GROQ_API_KEY, TELEGRAM_BOT_TOKEN

make up       # builds images, starts postgres + backend + frontend
make seed     # populates agents, workflows, and mock payment data
```

| Service  | URL                        |
|----------|----------------------------|
| Frontend | http://localhost:3000       |
| Backend  | http://localhost:8000       |
| API docs | http://localhost:8000/docs  |

---

## Demo

[![AgentOps Studio Demo](https://img.youtube.com/vi/tYDgstYFCkM/maxresdefault.jpg)](https://youtu.be/tYDgstYFCkM)

*▶ Click to watch — Telegram trigger → 5 agents → live timeline → customer response (5 min)*

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                     Frontend                         │
│  Next.js 14 · TypeScript · Tailwind · @xyflow/react │
│  Agent CRUD · Visual Workflow Builder · Run Monitor  │
└────────────────────┬────────────────────────────────┘
                     │ HTTP / WebSocket
┌────────────────────▼────────────────────────────────┐
│                   API Layer                          │
│  FastAPI · REST endpoints · WebSocket /ws/{run_id}  │
│  /agents  /workflows  /runs  /runs/{id}/timeline    │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│                 Service Layer                        │
│  RuntimeService  ·  ObservabilityService            │
│  asyncio.create_task → _execute_run (background)    │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│                Runtime Layer                         │
│  WorkflowCompiler · LangGraph StateGraph            │
│  Agent nodes · Condition routers · MemorySaver      │
│  GuardrailEvaluator · Tool Registry (6 tools)       │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│               PostgreSQL 16                          │
│  Domain tables: agents, workflows, runs, run_steps, │
│  messages, tool_calls, token_usage                  │
│  Mock tables: mock_transactions, mock_psp_status,   │
│  mock_routing_logs                                  │
└─────────────────────────────────────────────────────┘

Telegram polling runs as an asyncio background task inside
the backend container — no public URL or webhook needed.
```

**Four layers, clean boundaries:**

- **API layer** — FastAPI routers translate HTTP/WebSocket into service calls. No business logic here; it only validates input and serialises output.
- **Service layer** — `RuntimeService` creates a `Run` row and fires `asyncio.create_task(_execute_run(...))`, returning immediately. `ObservabilityService` records every message, tool call, and token usage event while a run is in progress and broadcasts them over WebSocket.
- **Runtime layer** — `WorkflowCompiler` converts a React Flow graph_json DAG into a compiled LangGraph `StateGraph`. Agent nodes run an LLM + tool loop; condition nodes are pure routing functions; the end node composes the final customer message in Python.
- **Database** — a single PostgreSQL 16 instance stores both domain data and mock payment fixtures. LangGraph checkpoints are written to Postgres via `AsyncPostgresSaver` when available, falling back to `MemorySaver`.

---

## 3. Why LangGraph

**DAG compilation.** The workflow builder saves a React Flow graph as `graph_json` — a plain JSON object with `nodes` and `edges` arrays. `WorkflowCompiler.compile()` walks this structure once at run start and produces a compiled LangGraph `StateGraph`. Agent nodes become async coroutines; condition nodes become `add_conditional_edges` routing functions. The visual DAG and the runtime execution model stay in 1-to-1 correspondence without any custom graph traversal code.

**Checkpoint persistence.** LangGraph's `AsyncPostgresSaver` writes the full `WorkflowState` after every node execution. If the backend restarts mid-run, the graph can resume from the last checkpoint by passing the same `thread_id` (which is the `run_id`). At this scope the platform uses `MemorySaver` as a fallback when `psycopg[binary]` is not available; switching to Postgres checkpoints requires one dependency addition and a rebuild.

**Versus alternatives.** A hand-rolled FSM would require reimplementing branching, state accumulation, and retry logic. Prefect and Airflow are task orchestrators designed for data pipelines — they carry significant operational overhead and do not have first-class support for LLM tool loops. LangGraph's abstraction level matches the problem exactly: a stateful, conditional, multi-step agentic process where each step is an LLM call, not a deterministic function.

---

## 4. Why Telegram

**No public URL required.** Telegram's polling model works from behind a NAT, inside a Docker container, on a laptop — anywhere with outbound HTTPS. The `TelegramAdapter.start()` method calls `updater.start_polling(drop_pending_updates=True)` as an asyncio background task, which means there is no infrastructure dependency beyond the Telegram API. Webhook-based alternatives (WhatsApp, Slack Events API) require a publicly reachable HTTPS endpoint, which adds complexity during local development and demos.

**Extensibility.** All channel adapters inherit from `ChannelAdapter` (an ABC defined in `app/channels/base.py`) with three methods: `start()`, `stop()`, and `send(recipient, text)`. Adding WhatsApp or Slack means implementing those three methods and registering the adapter in the lifespan handler. The runtime layer and workflow compiler are unaware of the channel — they only see `trigger_channel: str` in the `Run` row and `trigger_payload: dict` in `WorkflowState`.

---

## 5. Why No Redis / Celery

FastAPI's `asyncio.create_task` is sufficient for this scope. When a workflow is triggered, `RuntimeService.trigger_run()` commits the `Run` row, schedules `_execute_run(...)` as an asyncio task in the same event loop, and returns the pending `Run` immediately. The background task runs concurrently with incoming HTTP requests — no broker, no worker process, no deployment complexity.

The tradeoff is that tasks are not durable across restarts. A production path would replace `asyncio.create_task` with a task queue (Redis + Celery, or Postgres-backed with `pgqueuer`) while keeping the `_execute_run` coroutine unchanged. The interface boundary is the `run_id` string passed to that function — nothing else in the codebase needs to change.

---

## 5a. Smart Routing

Incoming Telegram messages are automatically routed to the correct workflow based on configurable keyword rules — no code changes required.

### How it works

When a message arrives on Telegram, the platform checks it against routing rules stored in the database, in priority order. The first rule whose keywords match the message determines which workflow runs.

Default rules:

| Keywords | Workflow |
|---|---|
| payment, transaction, TXN, failed, charged | Payment Failure Triage |
| urgent, down, support, help, account, login | Support Escalation |
| fraud, suspicious, verify, unauthorized, alert | Fraud Detection Alert |

### Configuring routing rules

Rules are managed entirely from the Settings page — no developer needed:

1. Open Settings → Smart Routing Rules
2. Add a new rule: enter keywords + select workflow
3. Drag to reorder priority (first match wins)
4. Toggle rules on/off without deleting them
5. Save — active immediately, no restart required

This means a non-technical ops manager can onboard a new workflow and have it live on Telegram in under 60 seconds.

---

## 6. Features Implemented

- [x] Agent CRUD — name, system prompt, model provider/name, temperature, tools allowlist, cost and iteration ceilings
- [x] Workflow builder — visual React Flow canvas with Agent, Condition, Trigger, and End node types
- [x] Workflow execution — LangGraph-compiled DAG, async background task, full audit trail
- [x] Condition routing — enum matching (case-insensitive) and numeric operators (eq, neq, gt, gte, lt, lte, in, not_in)
- [x] Reviewer retry guard — iteration_count ≥ 2 forces the success path to prevent infinite loops
- [x] Tool calling — LLM-driven tool loop with per-node deduplication, guardrail allowlist enforcement
- [x] Guardrails — iteration ceiling and cost ceiling checked before each agent node; tool allowlist enforced per call
- [x] Real-time monitoring — WebSocket stream of run events, live cost counter, step timeline, message log
- [x] Telegram integration — async polling, inbound message triggers active workflow, outbound reply after completion
- [x] Cost tracking — per-run token usage and USD cost computed from static price table, surfaced in UI
- [x] Final response composition — Python template function (no LLM) assembles customer-facing message from accumulated agent outputs
- [x] Docker Compose deployment — three services (postgres, backend, frontend), single `make up`
- [x] Smart Routing Rules — keyword-based automatic workflow routing stored in Postgres, evaluated in priority order
- [x] Routing Rules UI — non-technical users can configure routing from Settings without code changes
- [x] Dynamic routing — add, edit, delete, and reorder rules from the browser; changes are live immediately

---

## 7. Demo Scenario: Payment Failure Triage

A payment fails and the customer sends a Telegram message: *"My payment of $500 to ACME Store failed. Transaction TXN-0003."*

The platform routes between three workflows automatically based on message content:

- *"My payment of $150 failed. TXN-0003."* → **Payment Failure Triage**
- *"URGENT: Our system is down."* → **Support Escalation**
- *"Check TXN-0004 for fraud."* → **Fraud Detection Alert**

Routing rules are fully configurable from the Settings UI.

The active workflow routes the message through five agent nodes:

```
Telegram → Intake Agent → Investigator Agent
                               │
                    [condition: failure_type?]
                    ┌──────────┴──────────┐
              PSP_TIMEOUT          CARD_DECLINE / UNKNOWN
              INSUFFICIENT_FUNDS
                    │                     │
           Resolution Agent       Escalation Agent
                    └──────────┬──────────┘
                         Reviewer Agent
                               │
                   [condition: reviewer_score ≥ 7?]
                   ┌───────────┴───────────┐
                 yes (or retry ≥ 2)        no
                   │                  Reviewer (retry)
            Telegram Response              │
                   └───────────────────────┘
                         End Node
                   (compose_final_response)
```

**Four tools backed by Postgres mock tables:**

| Tool | Table | Purpose |
|------|-------|---------|
| `get_transaction` | `mock_transactions` | Fetch amount, PSP, failure_reason, error_code |
| `get_psp_status` | `mock_psp_status` | Check operational status and error rate for a PSP |
| `check_routing_logs` | `mock_routing_logs` | Retrieve multi-hop routing history for a transaction |
| `suggest_alternate_psp` | `mock_psp_status` | Return the operational PSP with the lowest error rate |

`calculator` and `send_telegram_message` are additional registered tools available to any agent via `tools_enabled`.

---

## 8. Data Model

| Table | Primary key | Purpose |
|-------|-------------|---------|
| `agents` | UUID | Agent configuration — prompt, model, tools, cost/iteration ceilings |
| `workflows` | UUID | Workflow metadata + full React Flow `graph_json` |
| `runs` | UUID | One execution of a workflow — status, cost, final_response |
| `run_steps` | UUID | One agent node invocation within a run — input, output, timing |
| `messages` | UUID | LLM conversation history (user / assistant / tool roles) per run |
| `tool_calls` | UUID | Individual tool invocations with input and output, linked to a step |
| `token_usage` | UUID | Prompt + completion tokens and estimated USD cost per agent step |

Mock tables (`mock_transactions`, `mock_psp_status`, `mock_routing_logs`) live in the same database and are seeded by `make seed`. They are read-only at runtime.

---

## 9. Runtime Flow

1. **Inbound message** — Telegram polling receives a message and calls `TelegramAdapter.on_message(sender, text, raw)`.
2. **Workflow lookup** — the adapter queries for the single active workflow and calls `RuntimeService.trigger_run(workflow_id, trigger_channel="telegram", trigger_payload={...})`.
3. **Run created** — a `Run` row is inserted with `status=pending`; `asyncio.create_task(_execute_run(...))` is scheduled; the HTTP response (or adapter call) returns immediately.
4. **Compilation** — `_execute_run` fetches the `Workflow` row and calls `WorkflowCompiler.compile(workflow)`, which walks `graph_json` and builds a `StateGraph`. The compiled graph is ephemeral — it is not cached between runs.
5. **Graph invocation** — `compiled.ainvoke(initial_state, config={"configurable": {"thread_id": run_id}})` drives the agent loop. Each agent node: fetches its `Agent` row, checks guardrails, calls the LLM with accumulated messages, executes any tool calls, writes `RunStep` / `ToolCall` / `TokenUsage` / `Message` rows, and broadcasts events over WebSocket.
6. **Condition routing** — after each agent node, the outgoing condition node evaluates `state["failure_type"]` or `state["reviewer_score"]` and returns the target node ID for the next step.
7. **End node** — `compose_final_response(state)` reads `current_output` (a merged dict of all agent outputs from every step) and `state["failure_type"]` to select and fill one of four Python message templates. The result is written to `runs.final_response`.
8. **Telegram reply** — `_execute_run` calls `send_response(chat_id, final_text)` to deliver the message back to the original sender.

---

## 10. Environment Variables

```bash
# ── Database ──────────────────────────────────────────────────────────────────
# asyncpg driver for async SQLAlchemy
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/yuno
# psycopg2 driver for Alembic migrations (sync)
SYNC_DATABASE_URL=postgresql+psycopg2://postgres:postgres@postgres:5432/yuno

# ── LLM providers (both free tier) ───────────────────────────────────────────
# Controls which provider the get_llm() factory defaults to (google | groq)
DEFAULT_MODEL_PROVIDER=google
DEFAULT_MODEL=gemini-1.5-flash
# https://aistudio.google.com/app/apikey
GOOGLE_API_KEY=your_google_api_key_here
# https://console.groq.com/keys
GROQ_API_KEY=your_groq_api_key_here

# ── Telegram ──────────────────────────────────────────────────────────────────
# Create a bot via @BotFather; paste the token here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
# Your personal chat ID (send /start to @userinfobot to find it)
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# ── App ───────────────────────────────────────────────────────────────────────
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
CORS_ORIGINS=http://localhost:3000
```

---

## 11. Running Locally

```bash
# Start all three services (postgres, backend, frontend) and rebuild images
make up

# Run database migrations (Alembic; already runs automatically on startup)
make migrate

# Populate agents, workflows, and mock payment data
make seed

# Run all 47 tests
make test

# Tail backend logs
make logs

# Open a shell inside the backend container
make shell
```

**First-run checklist:**
1. `cp .env.example .env` and fill in API keys
2. `make up` — wait ~30 seconds for postgres to become healthy
3. `make seed` — seeds are idempotent (DELETE + INSERT), safe to re-run
4. Open http://localhost:3000


---

## 13. Extending the Platform

### Adding a New Tool

1. Create a function in `backend/app/runtime/tools/` decorated with `@tool` from `langchain_core.tools`.
2. Import it in `backend/app/runtime/tools/__init__.py` and add it to `ALL_TOOLS`.
3. The tool is immediately available for selection in the Agent config UI under `tools_enabled`.

Tools that need database access should use `async with AsyncSessionLocal() as db:` — the same pattern used by `get_transaction` and the other payment tools. No registration beyond `ALL_TOOLS` is required.

### Adding a New Workflow Template

1. Define the graph as a `graph_json` dict (nodes + edges arrays) following the schema used in `app/seeds/seed_workflows.py`.
2. Either seed it to the database and load it in the UI via "Load Template", or hard-code it in the `TEMPLATES` dict inside `frontend/components/workflow-builder/Canvas.tsx`.

### Adding a New Messaging Channel

1. Create a class in `backend/app/channels/` that extends `ChannelAdapter` (`app/channels/base.py`) and implements `start()`, `stop()`, and `send(recipient, text)`.
2. Call `trigger_run(..., trigger_channel="your_channel", trigger_payload={...})` inside the message handler — identical to the Telegram adapter.
3. Register the adapter's `start()` and `stop()` in the FastAPI lifespan in `app/main.py`.

The runtime layer is channel-agnostic; only `trigger_channel` (a string) is stored on the `Run` row.

### Adding a New Routing Rule

**From the UI (no code required):**

1. Open Settings → Smart Routing Rules
2. Click "+ Add Rule"
3. Enter trigger keywords (e.g. `refund`, `chargeback`)
4. Select the target workflow from the dropdown
5. Drag to set priority (top = checked first)
6. Click "Save All Rules"

No code changes. No restart. Live immediately.

**Programmatically via the API:**

```http
POST /routing-rules
Content-Type: application/json

{
  "keywords": ["refund", "chargeback"],
  "workflow_id": "uuid-here",
  "priority": 4,
  "is_active": true
}
```

---

## 14. Tests

```bash
make test   # runs pytest inside the backend container — 47 tests, ~2s
```

| File | Tests | What it covers |
|------|-------|---------------|
| `test_agent_crud.py` | 8 | POST / GET / PATCH / DELETE `/agents`, duplicate-name 422, unique name isolation |
| `test_workflow_compile.py` | 10 | `WorkflowCompiler.compile()` smoke, router unit tests (enum matching, numeric gate, case-insensitivity, retry guard at iteration ≥ 2) |
| `test_workflow_execution.py` | 5 | Full `_execute_run` with mocked LLM: status=completed, ≥ 4 RunStep rows, final_response set, timestamps populated, graceful failure for missing workflow |
| `test_agent_handoff.py` | 5 | User message persisted on trigger, ≥ 4 assistant messages per run, correct run_id foreign key, non-empty content, ascending created_at order |
| `test_tool_execution.py` | 12 | `get_transaction` and `get_psp_status` against real seed data, `GuardrailEvaluator.filter_tool` (allowlist enforcement, empty-list no-restriction), `check_before_step` (iteration and cost ceilings) |
| `test_telegram_delivery.py` | 4 | `send_response` called once on telegram trigger with correct chat_id, not called for API trigger, run still completes when Telegram raises |
| `test_agents.py` | 3 | Health check, smoke create-and-get, 404 for missing UUID (pre-existing) |

All LLM calls are mocked via `pytest-mock` patching `app.runtime.compiler.get_llm`. No real API calls are made. Tests share a single session-scoped event loop to avoid asyncpg connection pool conflicts across tests.

---

## 15. Deliberate Tradeoffs

| Decision | What was cut | Production path |
|----------|-------------|-----------------|
| **Scheduler** | `cron_schedule` column and UI field exist but no execution engine | Replace `asyncio.create_task` with APScheduler or Celery Beat; the `_execute_run` interface is unchanged |
| **Auth / multi-tenancy** | Single user, no authentication on any endpoint | Add Clerk (or any OIDC provider) + `tenant_id` FK on every table; FastAPI middleware enforces row-level isolation |
| **Horizontal scaling** | One backend process; task state is in-process | Move background tasks to a Postgres-backed queue (`pgqueuer`) and run multiple backend replicas behind a load balancer |
| **Multi-channel routing** | Telegram implemented, `ChannelAdapter` ABC defined for Slack/WhatsApp | Implement `receive()`, `send()`, `parse_message()` per channel |
| **Workflow versioning** | `graph_json` is overwritten on every save | Add a `workflow_versions` table with a `version` integer; runs store `workflow_version_id` instead of `workflow_id` |
| **Multi-provider LLM** | `get_llm()` factory supports `google`, `groq`, and `ollama`; Gemini Flash is the default | Set `DEFAULT_MODEL_PROVIDER=groq` or `ollama` in `.env` to switch; per-agent overrides already stored in `model_provider` / `model_name` columns |

---

## 16. Cost Model

Both LLM providers used here offer free tiers with no credit card required. Gemini 1.5 Flash (Google AI Studio) and Llama 3.3 70B Versatile (Groq) are **free within their respective rate limits** for development use.

The platform tracks cost per run using a static price table in `app/services/observability_service.py` (`MODEL_PRICES`). Prices are estimates as of May 2026 and may not reflect current provider pricing. The cost display in the UI is informational — actual charges depend on your account tier with each provider.

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|-----------------------|------------------------|
| `gemini-1.5-flash` | $0.075 | $0.30 |
| `gemini-1.5-pro` | $3.50 | $10.50 |
| `llama-3.3-70b-versatile` | $0.59 | $0.79 |
| `llama-3.1-8b-instant` | $0.05 | $0.08 |

---

## 17. Future Improvements

- **Streaming responses** — pipe LLM token streams through the WebSocket so the UI renders partial agent output in real time instead of waiting for each node to complete.
- **Durable task queue** — replace `asyncio.create_task` with a Postgres-backed queue so in-flight runs survive backend restarts without Redis.
- **Graph versioning** — snapshot `graph_json` at trigger time so runs are always replayable against the exact workflow version that produced them.
