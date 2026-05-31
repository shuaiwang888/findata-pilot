# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FinDataPilot is a local-first financial data agent. It accepts natural-language financial queries, retrieves structured data from the WenCai (问财) `query2data` API, normalizes results into pandas DataFrames, persists trace records to MySQL, exports CSV/Parquet files, and serves both an API and a React web workbench.

## Commands

```bash
# Start the full service (installs deps, inits MySQL, starts uvicorn)
bash start.sh                              # → http://127.0.0.1:8011

# Backend only
uvicorn app.main:app --host 127.0.0.1 --port 8011

# Python syntax check
python3 -m compileall app scripts

# Frontend
cd web && npm install
npm run dev                                # Vite dev server → http://127.0.0.1:5173
npm run build                              # Outputs to ../app/web_dist

# Health check
curl http://127.0.0.1:8011/health

# CLI query
python3 scripts/data_agent_cli.py --query "市盈率低于15的科技股" --limit 100

# Find leaked secrets (from README)
rg -n "sk-[A-Za-z0-9_-]+|password|api[_-]?key|secret|token|/Users/" . \
  -g '!web/node_modules/**' -g '!outputs/**' -g '!app/web_dist/**' -g '!**/__pycache__/**'
```

## Architecture

```
User Query → FastAPI Router (/chat or /chat/stream)
  → Planner (keyword-based + MiniMax LLM, with fallback)
    → QUERY2DATA() → WenCai API → pandas DataFrame
      → Analysis (optional: moving_average, return, volatility, max_drawdown)
        → Save (CSV + Parquet + MySQL)
          → Summarizer (MiniMax or local fallback)
            → Response (JSON or SSE stream) → React frontend
```

### Backend (`app/`)

| Directory | Role |
|-----------|------|
| `app/api/` | FastAPI route handlers: `chat.py` (POST /chat, /chat/stream), `health.py`, `history.py`, `files.py` |
| `app/agent/` | Core pipeline: `planner.py` (keyword-based planning), `executor.py` (orchestrates full pipeline), `llm_assistant.py` (MiniMax planner/summarizer), `streaming.py` (SSE events), `analysis.py` (local pandas-based secondary analysis) |
| `app/tools/` | External API clients: `iwencai_client.py` → `query2data.py` (returns DataFrame), `minimax_client.py` |
| `app/storage/` | MySQL persistence: `schema.sql` (3 tables), `mysql.py` (connection), `repository.py` (CRUD for query runs) |
| `app/utils/` | `env.py` (loads .env), `trace.py` (64-char hex trace IDs), `dataframe.py` (save CSV/Parquet) |

The main orchestration function is `execute_query()` in `app/agent/executor.py`.

### Frontend (`web/`)

React 18 + TypeScript + Vite 7 + Ant Design 5 + ECharts 5 + TanStack React Query 5.

- `src/App.tsx` — Ant Design Layout with sidebar (QueryRuns) and content (ChatWorkbench + VisualSummary)
- `src/api/client.ts` — API client with SSE stream parsing for /chat/stream
- `src/components/ChatWorkbench.tsx` — Chat UI with progress bar and plan step collapse
- `src/components/VisualSummary.tsx` — ECharts auto-generation (bar/line/pie) + Ant Table + report sections
- `src/components/QueryRuns.tsx` — History sidebar with search and pagination
- `src/components/RunInfo.tsx` — Run detail inspector panel

Vite proxies `/chat`, `/history`, `/health`, `/files` to `localhost:8011` in dev mode. Build output goes to `app/web_dist/` and is served by FastAPI as static files.

### Fallback web UI

`app/web/index.html` is a comprehensive single-page fallback (no React needed) that handles the full chat/history/summary workflow with vanilla JS. Served when `app/web_dist/` doesn't exist.

## Graceful degradation

Every layer degrades gracefully:
- **MySQL unavailable** → API still works, writes warnings to logs; queries return results without persistence
- **MiniMax unavailable** → falls back to keyword-based planning and local DataFrame summarization
- **React build missing** → FastAPI serves the legacy `app/web/index.html` fallback page

## Environment variables

All config via `.env` (gitignored, template in `.env.example`):
- `IWENCAI_API_KEY` (required) — WenCai query2data API key
- `MINIMAX_API_KEY` (optional) — MiniMax LLM for planning/summarization
- `MINIMAX_MODEL` (default: `minimax-2.7`) — aliased to `MiniMax-M2.7`
- `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` — MySQL connection (database defaults to `data_agent`)
- `DATA_AGENT_OUTPUT_DIR` (default: `outputs/tables`) — CSV/Parquet export directory
- `DATA_AGENT_HOST/PORT` (default: `127.0.0.1:8011`) — FastAPI bind address
