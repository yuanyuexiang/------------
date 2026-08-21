"""招标文件包解压：递归 zip + GBK 文件名修复。

ECP 下载的招标文件包为多层嵌套 zip，且 zip 条目名以 GBK 编码写入
（zipfile 默认按 cp437 解码），需 cp437→gbk 还原，否则中文文件名乱码。
"""
from __future__ import annotations

import os
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import List

IGNORE_NAMES = {".DS_Store", "__MACOSX"}
NESTED_ZIP_MAX_DEPTH = 5


def fix_zip_name(name: str) -> str:
    """zip 条目名 cp437→gbk 还原；已是合法 UTF-8 的名字原样返回。"""
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    for enc in ("gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return name


@dataclass
class UnpackResult:
    root: str
    files: List[str] = field(default_factory=list)  # 相对 root 的路径


def _should_ignore(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return any(p in IGNORE_NAMES for p in parts)


def unpack(zip_path: str, dest: str, depth: int = 0) -> UnpackResult:
    """递归解压 zip_path 到 dest，返回全部落盘文件清单。

    嵌套 zip 解压到 `<原名去掉.zip>/` 同级目录，保留层次以便溯源。
    """
    result = UnpackResult(root=dest)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = fix_zip_name(info.filename)
            if name.endswith("/") or _should_ignore(name):
                continue
            out = os.path.join(dest, name)
            os.makedirs(os.path.dirname(out) or dest, exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if name.lower().endswith(".zip") and depth < NESTED_ZIP_MAX_DEPTH:
                sub_dest = out[:-4]
                sub = unpack(out, sub_dest, depth + 1)
                result.files.extend(
                    os.path.relpath(os.path.join(sub.root, f), dest) for f in sub.files
                )
            else:
                result.files.append(name)
    return result
