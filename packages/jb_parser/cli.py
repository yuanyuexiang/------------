"""CLI: jb-parse <招标文件包.zip> [-o trm.json]（或 python -m jb_parser.cli）"""
import argparse
import sys

from .pipeline import parse


def main() -> int:
    ap = argparse.ArgumentParser(description="Jinbang 招标文件包解析器")
    ap.add_argument("zip_path")
    ap.add_argument("-o", "--out", help="输出 TRM JSON 路径")
    ap.add_argument("-w", "--workdir", help="解压工作目录（默认临时目录）")
    args = ap.parse_args()
    trm = parse(args.zip_path, args.workdir)
    print(trm.summary())
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(trm.model_dump_json(indent=2))
        print("TRM 已写入:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
