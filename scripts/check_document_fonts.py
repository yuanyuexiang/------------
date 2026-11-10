"""核对当前 Gotenberg 字体环境；只读，不安装或替换字体。"""
import argparse
import json
import subprocess
from pathlib import Path

from jb_docgen.font_audit import report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('documents', nargs='+')
    args = parser.parse_args()
    output = subprocess.run(['docker', 'compose', 'exec', '-T', 'gotenberg',
                             'fc-list', '--format=%{family}\\n'], check=True,
                            capture_output=True, text=True).stdout
    families = sorted({f.strip() for line in output.splitlines() for f in line.split(',')})
    print(json.dumps({str(Path(p)): report(p, families) for p in args.documents}, ensure_ascii=False, indent=2))
