"""把 data/company_profiles/*.json 导入数据库 profiles 表（幂等 upsert）。

用法：python scripts/import_profiles.py [目录]
"""
import glob
import os
import sys

from jb_kb.models import CompanyProfile
from jb_store import Profile, init_db, session


def main() -> int:
    d = sys.argv[1] if len(sys.argv) > 1 else "data/company_profiles"
    init_db()
    n = 0
    for path in glob.glob(os.path.join(d, "*.json")):
        cp = CompanyProfile.load(path)
        name = cp.name or os.path.splitext(os.path.basename(path))[0]
        with session() as s:
            row = s.get(Profile, name)
            if row is None:
                s.add(Profile(name=name, credit_code=cp.credit_code, data=cp.model_dump()))
            else:
                row.credit_code, row.data = cp.credit_code, cp.model_dump()
        n += 1
        print("导入:", name)
    print(f"完成 {n} 份")
    return 0


if __name__ == "__main__":
    sys.exit(main())
