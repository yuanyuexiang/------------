# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

**Jinbang（金榜）**：面向国家电网供应商的智能投标文件编制系统。导入 ECP 平台下载的招标文件包（zip），解析为结构化的 TRM（招标要求模型），结合企业知识库生成商务/技术/价格投标文件，并做合规审查与模拟评分。原型 S1–S5 主线已完成（见 `docs/原型交付说明.md`），进入 P2 完善期。

总方案、Sprint 计划、国网业务规则（否决规则库、评分模板、真实文件结构实测）都在 `docs/`——**改业务逻辑前先读 `docs/国网真实招标文件结构分析.md`**，解析器的每个约定（GBK 文件名、表格变体、xlsx 表头位置）都来自那份实测记录，不是随意选择。

## 常用命令

```bash
pip install -e ".[dev]"        # 安装（导入名 jb_parser / jb_api；须 pip>=21.3）
pytest -q                      # 回归测试（依赖 物资/、服务/ 下的真实样本，缺样本自动 skip）
pytest -q -k shaanxi           # 单跑一个样本用例
alembic -c deploy/alembic.ini upgrade head   # 建表/迁移（本地 SQLite）
ruff check packages apps tests scripts # lint（提交前必须 clean）
python scripts/demo.py [--llm]   # 端到端 Demo（真实样本）
jb-parse <招标文件包.zip> -o trm.json          # CLI 解析
uvicorn jb_api.main:app --reload --port 8000  # 后端
cd apps/jb-web && npm install && npm run dev  # 前端（5173，/api 代理到 8000）
docker compose up -d --build   # 部署：web(8080)/api/pgvector/redis/minio；--profile docgen|llm 追加
```

## 架构（读代码前必须知道的）

**薄 API + 厚领域包**（六边形架构）：`apps/jb_api` 只做路由/校验/调度，业务逻辑全部在 `packages/`。铁律：`packages/` 不得 import `apps/` 或任何 Web 框架；删掉 `apps/` 后 `pytest` 必须照样全绿。前后端分离是另一维度：`apps/jb-web`（React/Vite/AntD，kebab-case 是 npm 惯例）独立于 `apps/jb_api`（snake_case 是 Python 惯例），REST 通信。

**持久层 `jb_store`**：Pydantic 对象是真源，数据库只做落盘（TRM/档案以 JSON 列整体存取，需检索的列单独冗余）。表结构改动必须走 Alembic（`alembic -c deploy/alembic.ini revision --autogenerate`），字段只增不删。`Project.trm` 是机器解析版，`trm_confirmed` 是确认页人工版，下游一律优先用后者。

**流水线全景**：`jb_parser`（解析→TRM）→ `jb_agents.qualify`（资格自检）→ `jb_agents.writer`（LLM 起草，带溯源）→ `jb_docgen`（参数自动填 + 商务/技术文件 + 导出加固）→ `jb_rules`（否决规则引擎）→ `jb_agents.scorer`（模拟评分）→ `jb_agents.price`（价格校验/基准价模拟）。`jb_kb` 提供档案与检索，`jb_llm` 是唯一的模型出口，`jb_store` 落盘。`scripts/demo.py` 一键跑全链路。

**jb_parser 流水线**（`pipeline.parse()` 为唯一入口）：
`unpack`（递归 zip + GBK 文件名修复）→ `classify`（按实测命名规律分类文件）→ `docx_utils`（六章切分/表格结构化）→ `extract` + `scoring` + `normalize`（前附表/否决表/提交方式表/技术参数表/评分模板/关键条件）→ `trm`（Pydantic Schema，全流程唯一真源）。

TRM Schema 演进规则：**字段只增不改名**（下游 Agent、前端、文档引擎都依赖它）。

## 领域约束（违反即产出废标文件，优先级高于一切工程偏好）

- 事实字段（企业名、资质、业绩、金额、日期）只能来自结构化数据填充，**永远不允许由 LLM 生成**；查不到就输出【待补充：xxx】标记，导出前强制清零。
- 解析抽不到的字段留 `None` + 原文引用，绝不猜测默认值——人工确认页和 LLM 兜底靠 None 判断。
- 国网招标文件同名表格存在多省变体（提交方式表已知 2 种、前附表已知 3/4 列两种），新增变体时扩展现有 extractor 的兼容分支并为对应样本加断言，不要另写并行函数。
- 系统定位是供应商**自用**工具（国网禁止委托中介编制标书）：不得实现"同一批次同一包服务多家投标人"的能力。

## 工程约定与已知坑

- **Python 3.9 兼容**：Pydantic 在运行时求值注解，PEP 604 的 `X | None` 会崩——用 `Optional[X]`；ruff 已禁 UP007/UP045（pyproject 有注明），不要"顺手现代化"。
- **ECP zip 文件名是 GBK**：必须走 `unpack.fix_zip_name()`（cp437→gbk），直接 `unzip` 会乱码。
- **ECP 生成的 xlsx 缺 dimension 元数据**：openpyxl read_only 模式只读出 1 行，必须 `ws.reset_dimensions()`（见 `extract._load_ws`）。
- 附件类 xlsx 表头通常在第 3 行，货物清单在第 1 行——用 `_detect_header` 探测，不要写死行号。
- 测试样本（`物资/`、`服务/`，约 1.4GB）被 gitignore，是冻结的固定测试集：**不要修改、不要提交、不要在测试外的代码里引用其绝对路径**。
- 提交信息用中文，正文列条目；提交前 `ruff check` 与 `pytest` 必须通过。

## 当前欠债（有意为之，接手时按计划还，勿提前"顺手修"）

- 知识库目前以 CompanyProfile 整体 JSON 存 `profiles` 表，S2 后半拆为多表（证照/人员/业绩）后才能做字段级检索与有效期预警
- Celery 模式只在 compose（Redis）下生效，本地/测试为进程内 BackgroundTasks；两者共用 `jb_api.tasks.run_parse`，改任务逻辑只改这一处
- LLM 兜底已接（`jb_llm`，配置在 .env，key 绝不入库）；golden 标注集未建（等业务专家），建成后放 `tests/golden/`
