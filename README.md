# FinDataPilot

FinDataPilot is a local-first financial data agent. It accepts natural-language financial queries, retrieves structured data through WenCai `query2data`, normalizes results into DataFrames, persists trace records to MySQL, exports CSV/Parquet files, and serves both API/CLI and a web workbench.

Recommended repository name: `findata-pilot`.

## Features

- Natural-language financial data query through WenCai `query2data`
- Structured DataFrame normalization and preview
- Full query tracing in MySQL database `data_agent`
- CSV and Parquet export under `outputs/tables/`
- FastAPI endpoints for health, chat, streaming chat, files, and history
- CLI entrypoint for local automation
- MiniMax-powered planning and result summarization, with local fallback
- React/Vite web workbench plus legacy static fallback page

## Requirements

- Python 3.10+
- MySQL 8.x or compatible MySQL server
- WenCai API key
- Optional: MiniMax API key for LLM planning and summarization
- Optional for frontend development: Node.js 18+

## Quick Start

1. Clone the repository.

```bash
git clone <your-repo-url>
cd findata-pilot
```

2. Create local environment config.

```bash
cp .env.example .env
```

Edit `.env` and fill in your own keys and database credentials. Do not commit `.env`.

3. Start the service.

```bash
bash start.sh
```

The service starts at:

```text
http://127.0.0.1:8011/
```

Health check:

```bash
curl http://127.0.0.1:8011/health
```

## Configuration

Environment variables are loaded from `.env` by `start.sh` and by the Python app.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `IWENCAI_API_KEY` | Yes | empty | WenCai `query2data` API key. |
| `MINIMAX_API_KEY` | No | empty | MiniMax API key for planning and summarization. If unset or unavailable, FinDataPilot uses fallback summaries. |
| `MINIMAX_MODEL` | No | `minimax-2.7` | MiniMax model alias. |
| `MINIMAX_BASE_URL` | No | `https://api.minimaxi.com/v1` | MiniMax API base URL. |
| `MYSQL_HOST` | No | `127.0.0.1` | MySQL host. |
| `MYSQL_PORT` | No | `3306` | MySQL port. |
| `MYSQL_USER` | No | `root` | MySQL user. |
| `MYSQL_PASSWORD` | No | empty | MySQL password. |
| `MYSQL_DATABASE` | No | `data_agent` | Database used for query tracing. |
| `DATA_AGENT_OUTPUT_DIR` | No | `outputs/tables` | CSV/Parquet export directory. |
| `DATA_AGENT_HOST` | No | `127.0.0.1` | FastAPI bind host. |
| `DATA_AGENT_PORT` | No | `8011` | FastAPI bind port. |
| `DATA_AGENT_PYTHON` | No | auto-detect | Python interpreter path used by `start.sh`. |

Example `.env`:

```bash
IWENCAI_API_KEY=your_iwencai_key
MINIMAX_API_KEY=your_minimax_key
MINIMAX_MODEL=minimax-2.7
MINIMAX_BASE_URL=https://api.minimaxi.com/v1

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=data_agent

DATA_AGENT_OUTPUT_DIR=outputs/tables
DATA_AGENT_HOST=127.0.0.1
DATA_AGENT_PORT=8011
```

## Database

`start.sh` initializes the schema from:

```text
app/storage/schema.sql
```

The schema creates database `data_agent` and these trace tables:

- `agent_query_runs`
- `agent_query_columns`
- `agent_query_rows`

If MySQL is unavailable, the API still starts. Queries can still return data and files, while persistence failures are reported in response warnings.

Manual initialization:

```bash
mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p < app/storage/schema.sql
```

## API Usage

Health:

```bash
curl http://127.0.0.1:8011/health
```

Normal chat:

```bash
curl -X POST http://127.0.0.1:8011/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"贵州茅台最新收盘价","limit":"1","save":true}'
```

Streaming chat:

```bash
curl -N -X POST http://127.0.0.1:8011/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"query":"st绝味近一周的涨跌幅","limit":"10","save":true}'
```

History:

```bash
curl http://127.0.0.1:8011/history
```

## CLI Usage

```bash
python3 scripts/data_agent_cli.py --query "贵州茅台最新收盘价" --limit 1
```

Disable persistence and file export:

```bash
python3 scripts/data_agent_cli.py --query "贵州茅台最新收盘价" --limit 1 --no-save
```

## Web Frontend

The FastAPI root path serves the built React app from `app/web_dist/` when present. If no React build exists, it falls back to the legacy static page in `app/web/index.html`.

Frontend source lives in:

```text
web/
```

Development:

```bash
cd web
npm install
npm run dev
```

Production build:

```bash
cd web
npm run build
```

Build output is generated under `app/web_dist/` and is intentionally ignored by Git.

## Project Structure

```text
app/
  agent/        Planning, execution, streaming, summarization
  api/          FastAPI routers
  storage/      MySQL schema and repositories
  tools/        WenCai and MiniMax clients
  utils/        Env, trace, DataFrame helpers
  web/          Legacy static web page
scripts/        CLI and utility scripts
web/            React/Vite frontend source
```

Runtime-generated directories are ignored:

- `outputs/`
- `logs/`
- `app/web_dist/`
- `web/node_modules/`
- `samples/`
- `docs/`
- `log.md`

## Security Notes

- Do not commit `.env`.
- Do not commit real API keys, database passwords, exported query outputs, or sample data containing private schemas.
- `.gitignore` excludes local secrets, runtime outputs, dependency directories, build artifacts, Python caches, CSV files, and Parquet files.
- Before pushing, run:

```bash
rg -n "sk-[A-Za-z0-9_-]+|password|api[_-]?key|secret|token|/Users/" . \
  -g '!web/node_modules/**' \
  -g '!outputs/**' \
  -g '!app/web_dist/**' \
  -g '!**/__pycache__/**'
```

## Development Checks

Python compile check:

```bash
python3 -m compileall app scripts
```

Git status:

```bash
git status --short --branch
```

## GitHub Upload

After creating an empty GitHub repository:

```bash
git remote add origin <github-url>
git push -u origin main
```

Use a private repository if your local history or future commits may contain proprietary query examples, schemas, or exported data.
