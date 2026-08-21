"""建档脚本：从南京百恩特真实投标文件生成企业档案（测试企业A）。

用法：python scripts/build_profile_baiente.py
输出：data/company_profiles/南京百恩特.json（data/ 已 gitignore，含真实企业信息不入库）
"""
import glob
import sys

from jb_kb import build_profile

DOCS = [
    "服务/2/132673-9012008-2037-南京百恩特自动化科技有限公司-云平台电子商务文件-包14.包15.包16.docx",
    "服务/2/132673-9012008-2037-南京百恩特自动化科技有限公司-云平台电子技术文件-包16.docx",
    "服务/1/技术文件-147、148.docx",
]

def main() -> int:
    docs = [d for d in DOCS if glob.glob(d)]
    if not docs:
        print("样本文件缺失")
        return 1
    p = build_profile(docs)
    out = "data/company_profiles/南京百恩特.json"
    p.save(out)
    print(f"档案已写入 {out}")
    print(f"  企业: {p.name} ({p.credit_code}) 注册资本{p.registered_capital_wan}万 员工{p.staff_total}")
    print(f"  证书 {len(p.certificates)} 项 | 人员 {len(p.personnel)} 人 | 业绩 {len(p.performances)} 项 | 财务 {len(p.financials)} 年度")
    for x in p.personnel:
        print("   人员:", x.name, x.credentials)
    for x in p.performances[:6]:
        print("   业绩:", x.project[:40], x.evidence)
    return 0

if __name__ == "__main__":
    sys.exit(main())
