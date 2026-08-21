# Jinbang（金榜）

国网智能投标 Agent 系统——面向国家电网供应商的投标文件编制系统。

方案与调研文档见 `docs/`（总方案：《国网智能投标Agent系统-完整技术方案.md》；开发依据：《原型开发计划.md》）。
真实招标文件样本（原型固定测试集）在 `物资/`、`服务/` 目录，体积大、不入 git。

## 架构

前后端分离（独立工程、REST 通信）+ 后端"薄 API、厚领域包"：

```
apps/jb-web/          前端 React SPA（Vite + AntD + TanStack Query），dev 端口 5173，/api 代理到 8000
apps/jb_api/          后端 FastAPI（只做路由/校验/调度，不写业务逻辑），端口 8000
packages/jb_parser/   S1 解析器：ECP 招标文件包 → TRM（招标要求模型）
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
pip install -r requirements.txt
python3 -m packages.jb_parser.cli <招标文件包.zip> -o trm.json   # CLI 解析
python3 -m pytest tests/ -q                                      # 回归测试

uvicorn apps.jb_api.main:app --reload --port 8000                # 后端
cd apps/jb-web && npm install && npm run dev                     # 前端（localhost:5173）
```

## 已知边界（S1 内迭代）

- 江苏服务样本的第六章提交表表头与陕西物资版不同，暂未命中（0 项）
- 批次级 zip 的批次号需从公告补抽；服务类规范书为叙述式，参数表按物资口径不适用
- 评分细则 xlsx（评标办法前附表之三~六引用的模板）结构化在 S1 后半段
