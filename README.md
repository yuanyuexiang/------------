# Jinbang（金榜）

国网智能投标 Agent 系统——面向国家电网供应商的投标文件编制系统。

方案与调研文档见 `docs/`（总方案：《国网智能投标Agent系统-完整技术方案.md》；开发依据：《原型开发计划.md》）。
真实招标文件样本（原型固定测试集）在 `物资/`、`服务/` 目录，体积大、不入 git。

## 架构

前后端分离（独立工程、REST 通信）+ 后端"薄 API、厚领域包"：

```
apps/jb-web/          前端 React SPA（Vite + AntD + TanStack Query），dev 端口 5173，/api 代理到 8000
apps/jb_api/          后端 FastAPI（只做路由/校验/调度，不写业务逻辑），端口 8000，导入名 jb_api
packages/jb_parser/   S1 解析器：ECP 招标文件包 → TRM（招标要求模型）；--llm 启用 LLM 兜底
packages/jb_llm/      LLM 客户端（OpenAI 兼容；配置走 .env：LLM_BASE_URL/LLM_API_KEY/LLM_MODEL）
packages/jb_kb/       企业知识库：档案模型、多表仓储（repo）、有效期预警（expiry）、附件（attachments）、从历史投标文件建档
packages/jb_agents/   业务 Agent：资格自检（jb-qualify）→ 可投性矩阵
packages/jb_store/    持久层：SQLAlchemy（本地 SQLite jinbang.db / compose PostgreSQL），Alembic 迁移在 deploy/alembic；projects.py 投标项目阶段/事件/截止日
packages/jb_docgen/   文档引擎：数值比较、技术参数自动填写、商务/技术文件生成、【待补充】阻断、导出加固
packages/jb_rules/    否决规则引擎（否决情形表 + 典型案例库 SG 规则）
packages/jb_agents/   资格自检 / 起草 writer / 价格 price / 评分 scorer
  unpack.py           递归 zip 解压 + GBK 文件名修复
  classify.py         包内文件分类（主文件/公告/规范书/清单/评分细则…）
  docx_utils.py       六章切分、表格结构化
  extract.py          前附表/否决表/提交方式表/技术参数表/xlsx 附件抽取
  trm.py              TRM Pydantic Schema
  pipeline.py         流水线（批次级 zip / 包级 zip 均可）
  cli.py              命令行入口
tests/                真实样本冒烟回归（样本在 物资/、服务/ 目录）
docs/                 项目文档（方案/计划/调研分析/否决案例库）
```

## 使用

```bash
pip install -e ".[dev]"                       # 安装（含开发依赖）；导入名 jb_parser / jb_api
jb-parse <招标文件包.zip> -o trm.json          # CLI 解析（加 --llm 启用兜底）
jb-qualify <包.zip> --profile data/company_profiles/xxx.json --llm   # 资格自检
pytest -q                                     # 回归测试

alembic -c deploy/alembic.ini upgrade head     # 建表/迁移（本地 SQLite；compose 启动时自动执行）
python scripts/import_profiles.py             # 把 data/company_profiles/*.json 导入知识库（主档 + 子表）
uvicorn jb_api.main:app --reload --port 8000  # 后端（无 CELERY_BROKER_URL 时任务进程内执行）
cd apps/jb-web && npm install && npm run dev  # 前端（localhost:5173）
```

命名约定：Python 包用 snake_case（`jb_api`、`jb_parser`），npm 工程用 kebab-case（`jb-web`）——
分别遵循各生态惯例，属有意为之。

## Docker Compose 部署

```bash
cp .env.example .env            # 修改口令
docker compose up -d --build    # jb-web(8080) / jb-api / jb-worker(celery) / pg+pgvector / redis / minio
open http://localhost:8080
```

> 仓库目录须为 ASCII 路径（BuildKit 对含中文的构建上下文会报 `sharedkey contains non-printable ASCII`），
> 现目录名 `jinbang` 已满足。已在 Docker 29.7 / Compose 5.4 实测：PG 迁移、Celery 任务、Nginx 反代全链路通过。

按阶段追加：`--profile docgen`（gotenberg，S3 文档转 PDF）、`--profile llm`（LiteLLM 网关，
先在 deploy/litellm.yaml 填模型账号）。S2 接 Celery 后解开 compose 中 jb-worker 注释。
文件：`docker-compose.yml`、`deploy/`（Dockerfile.api / Dockerfile.web / nginx.conf / litellm.yaml）。

## 已知边界（S1 内迭代）

- 批次级 zip 的批次号需从公告补抽；服务类规范书为叙述式，参数表按物资口径不适用
- 前附表语义归一为正则确定性抽取，抽不到留 None（待 LLM 兜底 / 确认页人工补）
- 价格评分模板（docx 公式文档）仅登记名称，公式参数化在价格模块（S4）实现
