# FinDataPilot

> **本地优先 · 自然语言驱动的金融数据智能体**
> Local-first, natural-language-driven financial data agent.

<p align="center">
  <a href="README_EN.md">English</a> · <a href="README.md">简体中文</a>
</p>

<p align="center">
  <img src="docs/images/workbench-dark.png" alt="FinDataPilot Workbench" width="100%">
</p>

<p align="center">
  <em>从一句自然语言到结构化金融数据：规划 → 取数 → 清洗 → 可视化 → 落库 → 总结，一气呵成。</em>
</p>

---

## ✨ 它能做什么

| 能力 | 说明 |
|---|---|
| 🗣️ **自然语言取数** | 接收中文/英文金融问题，调用问财 `query2data` 拿回结构化数据 |
| 🧭 **LLM 智能规划** | MiniMax 大模型拆解意图、定字段、定口径（断网时本地规则兜底） |
| 📊 **智能可视化** | 表格 + 按数据特征自动选图（柱/折/饼），单值/少行/纯文本自动不画图 |
| 💾 **全链路落库** | MySQL 持久化 `query_runs` / `query_columns` / `query_rows`，CSV + Parquet 导出 |
| ⚡ **流式回答** | SSE 协议边生成边吐字，前端打字机效果实时呈现 |
| 🖥️ **多端入口** | FastAPI 服务、命令行、React 工作台、静态兜底页 |
| 🛡️ **优雅降级** | MySQL 不可用、LLM 不可用、React 包缺失 — 全部不致命 |

## 🖼️ 工作台一览

![FinDataPilot Workbench](docs/images/workbench-dark.png)

上图为一次完整查询（`最新交易日A股市场市值最大的5只股票`）的全链路：

1. **执行规划** — LLM 拆解意图，给出"按市值降序取前 5"的取数计划
2. **进度条 + 步骤** — 流式呈现每一步执行状态
3. **打字机回答** — 自然语言结论边生成边呈现
4. **结构化报告** — 结论 / 筛选口径 / 计算步骤 / 结果要点 / 数据明细 / 注意事项
5. **智能图表** — 5 条含可比数值列的数据自动匹配柱状对比图
6. **历史侧栏** — 历次查询可点开回看，自动落 MySQL

> 💡 ECharts 渲染器按需懒加载：首屏不下载，等用户首次提问后再异步拉取。首屏体积约 **387 kB gzip**。

---

## 🏗️ 架构

```
用户自然语言 → FastAPI (/chat 或 /chat/stream)
            → Planner  (关键词规则 + MiniMax LLM，断网降级)
              → QUERY2DATA() → 问财 API → pandas DataFrame
                → Analysis  (动量/收益/波动/回撤，可选)
                  → Storage (CSV + Parquet + MySQL 落库)
                    → Summarizer (MiniMax 或本地摘要)
                      → Response (JSON 或 SSE 流) → React 前端
```

### 目录结构

| 目录 | 职责 |
|---|---|
| `app/api/` | FastAPI 路由：`chat.py` `health.py` `history.py` `files.py` |
| `app/agent/` | 核心管线：`planner.py` `executor.py` `llm_assistant.py` `streaming.py` `analysis.py` |
| `app/tools/` | 外部客户端：`iwencai_client.py` → `query2data.py`，`minimax_client.py` |
| `app/storage/` | MySQL 持久化：`schema.sql` `mysql.py` `repository.py` |
| `app/utils/` | 工具：`env.py` `trace.py` `dataframe.py` |
| `web/` | React 18 + TypeScript + Vite 7 + Ant Design 5 + ECharts 5 + TanStack Query 5 |
| `scripts/` | CLI 与辅助脚本 |
| `app/web/` | 静态兜底单页（React 构建缺失时启用） |

---

## 🚀 快速开始

### 1. 克隆

```bash
git clone https://github.com/shuaiwang888/findata-pilot.git
cd findata-pilot
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入你的密钥和数据库信息（**不要提交 `.env`**）：

```bash
IWENCAI_API_KEY=your_iwencai_key          # 必填
MINIMAX_API_KEY=your_minimax_key          # 可选；不填走本地兜底
MINIMAX_MODEL=minimax-2.7                  # 可选
MINIMAX_BASE_URL=https://api.minimaxi.com/v1

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=data_agent
```

### 3. 启动服务

```bash
bash start.sh                              # → http://127.0.0.1:8011
```

`start.sh` 会：安装 Python/Node 依赖 → 初始化 MySQL schema → 构建前端 → 启动 uvicorn。

### 4. 健康检查

```bash
curl http://127.0.0.1:8011/health
# → {"status":"ok",...}
```

### 5. 命令行试一下

```bash
python3 scripts/data_agent_cli.py --query "市盈率低于15的科技股" --limit 100
```

---

## 📡 API 速查

| Endpoint | Method | 说明 |
|---|---|---|
| `/health` | GET | 健康检查 |
| `/chat` | POST | 同步取数 + 总结 |
| `/chat/stream` | POST | SSE 流式 |
| `/history` | GET | 历史取数记录 |
| `/files/{run_id}` | GET | 下载 CSV / Parquet |

```bash
# 同步
curl -X POST http://127.0.0.1:8011/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"贵州茅台最新收盘价","limit":"1","save":true}'

# 流式
curl -N -X POST http://127.0.0.1:8011/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"query":"st绝味近一周的涨跌幅","limit":"10","save":true}'
```

---

## 🗄️ 数据持久化

`start.sh` 自动从 `app/storage/schema.sql` 建库建表，建出三张表：

- `agent_query_runs` — 每次查询的元信息 + 总结
- `agent_query_columns` — 查询返回的列定义
- `agent_query_rows` — 查询返回的行数据

> ⚠️ MySQL 不可用时 **API 仍可工作**，只是不落库并在响应 `warnings` 里标注。

手动初始化：

```bash
mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p < app/storage/schema.sql
```

---

## 🛡️ 优雅降级矩阵

| 组件缺失 | 表现 |
|---|---|
| MySQL 不可用 | API 正常返回，警告 `database unavailable` |
| MiniMax 不可用 | 自动切到关键词规则 + 本地 DataFrame 摘要 |
| `app/web_dist/` 不存在 | FastAPI 自动服务 `app/web/index.html` 静态兜底 |
| `.env` 没填密钥 | 启动时打印清晰告警，但 CLI 仍可走 mock |

---

## ⚙️ 配置项

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `IWENCAI_API_KEY` | ✅ | — | 问财 `query2data` 密钥 |
| `MINIMAX_API_KEY` | ❌ | — | 大模型密钥；不填走本地兜底 |
| `MINIMAX_MODEL` | ❌ | `minimax-2.7` | 模型别名 |
| `MINIMAX_BASE_URL` | ❌ | `https://api.minimaxi.com/v1` | MiniMax API 入口 |
| `MYSQL_HOST/PORT/USER/PASSWORD` | ❌ | `127.0.0.1:3306 root` | MySQL 连接 |
| `MYSQL_DATABASE` | ❌ | `data_agent` | 数据库名 |
| `DATA_AGENT_OUTPUT_DIR` | ❌ | `outputs/tables` | CSV/Parquet 导出目录 |
| `DATA_AGENT_HOST/PORT` | ❌ | `127.0.0.1:8011` | FastAPI 绑定 |

---

## 🔒 安全提示

- **不要**把 `.env` 推上 GitHub
- **不要**在 issue / PR / commit message 里贴真实密钥或数据库密码
- 推送前可以跑一遍敏感信息扫描：

```bash
rg -n "sk-[A-Za-z0-9_-]+|password|api[_-]?key|secret|token|/Users/" . \
  -g '!web/node_modules/**' \
  -g '!outputs/**' \
  -g '!app/web_dist/**' \
  -g '!**/__pycache__/**'
```

## 📜 License

MIT — see `LICENSE` (添加后)。
