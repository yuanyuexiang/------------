"""CLI: jb-qualify <招标文件包.zip> --profile data/company_profiles/xxx.json [--llm] [-o report.md]"""
import argparse
import sys

from jb_kb.models import CompanyProfile
from jb_parser import parse

from .qualify import qualify


def main() -> int:
    ap = argparse.ArgumentParser(description="Jinbang 资格自检：输出可投性矩阵")
    ap.add_argument("zip_path")
    ap.add_argument("--profile", required=True, help="企业档案 JSON")
    ap.add_argument("--llm", action="store_true", help="启用 LLM（资格条款结构化 + 业绩类型匹配）")
    ap.add_argument("-o", "--out", help="输出 Markdown 报告路径")
    args = ap.parse_args()
    trm = parse(args.zip_path)
    if args.llm:
        from jb_parser.llm_fallback import enrich
        enrich(trm)
    profile = CompanyProfile.load(args.profile)
    rep = qualify(trm, profile, use_llm=args.llm)
    md = rep.markdown()
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
