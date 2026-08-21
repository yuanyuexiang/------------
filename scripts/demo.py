"""Demo：对真实样本跑完整流水线（不起服务，直接走 API TestClient）。

用法：python scripts/demo.py [--llm]   （--llm 启用起草/评分/资格匹配的 LLM 部分，约 5 分钟）
流程：导入招标包 → 解析 → 确认 TRM → 导入档案 → 资格自检 → 生成商务/技术文件 → 合规审查 → 模拟评分 → 递交矩阵 → 导出
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/demo.db")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="jb_demo_"))
os.environ.pop("CELERY_BROKER_URL", None)

from fastapi.testclient import TestClient  # noqa: E402
from jb_api.main import app  # noqa: E402
from jb_kb.models import CompanyProfile  # noqa: E402

LLM = "--llm" in sys.argv
SAMPLE = "服务/1/国网江苏省电力有限公司2026年服务第四次公开招标采购_招标文件包.zip"
SCORING_SAMPLE = "服务/2/国网福建电力2026年第三次服务类竞争性谈判采购_采购文件包.zip"
PROFILE = "data/company_profiles/南京百恩特.json"


def step(n, title):
    print(f"\n== 第{n}步 {title} ==")


def main() -> int:
    t0 = time.time()
    c = TestClient(app)
    with c:
        step(1, "导入招标文件包并解析")
        with open(SAMPLE, "rb") as f:
            r = c.post("/api/projects", files={"file": (os.path.basename(SAMPLE), f, "application/zip")}).json()
        pid = r["id"]
        task = c.get(f"/api/tasks/{r['task_id']}").json()
        print(task["message"])

        step(2, "人工确认 TRM（演示：补入评分模板库，确认版落库）")
        trm = c.get(f"/api/projects/{pid}/trm").json()
        # 江苏包只给了模板名；评分模板库在实际系统中全局维护，这里用福建样本内的官方模板补齐
        from jb_parser import parse
        trm["scoring_templates"] = [t.model_dump() for t in parse(SCORING_SAMPLE).scoring_templates]
        c.put(f"/api/projects/{pid}/trm", json=trm)
        print("确认版已保存；评分模板", len(trm["scoring_templates"]), "套")

        step(3, "导入企业档案（南京百恩特，含演示用产品与已审核话术）")
        cp = CompanyProfile.load(PROFILE)
        for p in cp.performances:
            p.buyer_is_end_user = True          # 演示：视作已人工确认最终用户
        for b in cp.boilerplates:
            b.approved = True
        cp.legal_person, cp.authorized_rep, cp.authorized_rep_title = "【待补充：法定代表人】", "朱可心", "商务经理"
        c.put(f"/api/profiles/{cp.name}", json=cp.model_dump())
        print(f"{cp.name}：业绩 {len(cp.performances)} 人员 {len(cp.personnel)} 话术 {len(cp.boilerplates)}")

        step(4, "资格自检")
        q = c.post(f"/api/projects/{pid}/qualify", params={"profile": cp.name, "llm": LLM}).json()["report"]
        for p in q["packages"]:
            print(f"  {p['pkg_no']} {p['project_name'][:30]} → {p['verdict']}")

        step(5, f"生成商务/技术文件{'（含 LLM 起草）' if LLM else ''}")
        g = c.post(f"/api/projects/{pid}/generate", params={"profile": cp.name, "pkg_index": 0, "with_draft": LLM}).json()
        gt = c.get(f"/api/tasks/{g['task_id']}").json()
        res = gt["result"]
        print("  文件:", res["files"], "| 待补充:", res["summary"]["todo_count"], "| 导出阻断:", res["summary"]["export_blocked"])

        step(6, "合规审查")
        rv = c.post(f"/api/projects/{pid}/review", params={"profile": cp.name}).json()
        print("  结论:", "存在否决项" if rv["blocked"] else "无否决项", rv["counts"])
        for f_ in rv["findings"][:6]:
            print(f"   [{f_['level']}] {f_['rule_id']} {f_['title']}：{f_['message'][:60]}")

        step(7, "模拟评分")
        sc = c.post(f"/api/projects/{pid}/score", params={"profile": cp.name, "llm": LLM, "task_id": g["task_id"]}).json()
        rep = sc["report"]
        print(f"  技术 {rep['tech_total']}/{rep['tech_max']}  商务 {rep['biz_total']}/{rep['biz_max']}  加权 {rep['weighted']}")
        print("  失分 Top3:", [(h["element"][:14], h["loss"]) for h in sc["heatmap"][:3]])

        step(8, "递交矩阵")
        sm = c.get(f"/api/projects/{pid}/submission-matrix").json()["rows"]
        from collections import Counter
        print("  ", dict(Counter(r["status"] for r in sm)))

        step(9, "导出（预期被待补充阻断）")
        ex = c.post(f"/api/projects/{pid}/export", params={"filename": res["files"][0]}).json()
        print("  ok:", ex["ok"], "| 阻断:", ex["blocked_count"], "处，如", ex["blocked_by"][:2])

    print(f"\n总耗时 {time.time()-t0:.0f}s；产出目录 {os.environ['UPLOAD_DIR']}/{pid}/out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
