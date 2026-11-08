"""用标准件对比生成件；报告留在调用者指定的本地路径，不改写原件。"""
import argparse
import json
from pathlib import Path

from jb_docgen.benchmark import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', help='标准 DOCX')
    parser.add_argument('candidate', help='待检查 DOCX')
    parser.add_argument('-o', '--output', required=True, help='本地 JSON 报告路径（包含客户资料）')
    args = parser.parse_args()
    report = compare(args.reference, args.candidate)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in (
        'missing_image_views', 'additional_image_views', 'missing_reference_headings')},
        ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
