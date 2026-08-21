"""解压产物文件分类。

分类依据为实测的 ECP 包命名规律（见《国网真实招标文件结构分析.md》§2）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# 类别常量
MAIN_DOC = "main_doc"            # 六章主文件 docx
ANNOUNCEMENT = "announcement"    # 第一章招标公告 docx
GOODS_DEMAND_XLSX = "goods_demand_xlsx"      # 附件：货物需求一览表
QUAL_PERF_XLSX = "qual_perf_xlsx"            # 附件：资质业绩一览表
GOODS_LIST_XLSX = "goods_list_xlsx"          # 货物清单（行项目级）
SERVICE_DEMAND_XLSX = "service_demand_xlsx"  # 服务类：本批需求一览表（每包评审办法+资格要求）
SPEC_DOC = "spec_doc"            # 技术规范书 docx
SCORING = "scoring"              # 评分细则（docx/xlsx）
CONTRACT = "contract"            # 合同文件
PRICE_SHEET = "price_sheet"      # 报价表 xls/xlsx（规范书随附）
SIGN = "sign"                    # 签名文件（忽略）
OTHER = "other"

_MAIN_PAT = re.compile(r"(招标文件\(|招标文件（|招标文件分册|采购文件\.docx$|采购文件（)")


@dataclass
class Manifest:
    root: str
    by_category: dict[str, list[str]] = field(default_factory=dict)

    def add(self, category: str, relpath: str) -> None:
        self.by_category.setdefault(category, []).append(relpath)

    def first(self, category: str):
        items = self.by_category.get(category) or []
        return items[0] if items else None


def classify_file(relpath: str) -> str:
    name = os.path.basename(relpath)
    lower = name.lower()
    if lower.endswith(".sign"):
        return SIGN
    if lower.endswith(".docx") or lower.endswith(".doc"):
        if "技术规范书" in name or "技术规范书" in relpath:
            return SPEC_DOC
        if _MAIN_PAT.search(name):
            return MAIN_DOC
        if "招标公告" in name or "采购公告" in name:
            return ANNOUNCEMENT
        if "合同" in name:
            return CONTRACT
        if "评分" in name or "详评" in name or "评分" in relpath or "详评" in relpath:
            return SCORING
        # 规范书目录下的正文 docx（如"…-综合网管1.docx"）也视作规范书
        if "技术规范" in relpath or re.search(r"\([A-Z0-9]{4}-\d{9}-\d{5}\)", relpath):
            return SPEC_DOC
        return OTHER
    if lower.endswith((".xlsx", ".xls")):
        if "货物需求" in name:
            return GOODS_DEMAND_XLSX
        if "资质业绩" in name:
            return QUAL_PERF_XLSX
        if "货物清单" in name:
            return GOODS_LIST_XLSX
        if "需求一览表" in name:
            return SERVICE_DEMAND_XLSX
        if "报价" in name:
            return PRICE_SHEET
        if "评分" in name or "详评" in name or "细则" in name or "评分" in relpath or "详评" in relpath:
            return SCORING
        return OTHER
    return OTHER


def build_manifest(root: str, files: list[str]) -> Manifest:
    m = Manifest(root=root)
    for f in files:
        m.add(classify_file(f), f)
    return m
