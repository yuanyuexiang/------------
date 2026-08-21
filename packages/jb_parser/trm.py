"""TRM（招标要求模型）Schema——全流程唯一真源。

与《国网智能投标Agent系统-完整技术方案》§4.1 对应；原型先落关键子集，
字段只增不改名。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PrenoticeClause(BaseModel):
    """投标人须知前附表条目。"""
    clause_no: str = ""
    name: str = ""
    content: str = ""


class RejectionRule(BaseModel):
    """否决情形（评标办法前附表之二）。"""
    category: str = ""      # 形式评审/响应性评审/资格评审/其他
    aspect: str = ""        # 格式内容/文件签署/投标报价/...
    text: str = ""


class SubmissionItem(BaseModel):
    """提交方式表条目（第六章末尾，= 递交矩阵）。"""
    seq: str = ""
    item: str = ""
    channels: List[str] = Field(default_factory=list)
    port: str = ""          # 投标工具上传端口说明
    section: str = ""       # 价格文件/商务文件/技术文件


class SpecParamRow(BaseModel):
    """标准技术参数表行——"投标人保证值"为系统待填目标。"""
    row: int
    name: str = ""
    unit: str = ""
    required: str = ""      # 项目需求值或表述
    star: bool = False
    response: Optional[str] = None  # 投标人保证值（待填）


class SpecDoc(BaseModel):
    spec_id: str = ""       # 如 B006-500009678-00011；9999 前缀=固化规范
    title: str = ""
    source: str = ""        # 相对路径
    structured: bool = True
    param_rows: List[SpecParamRow] = Field(default_factory=list)


class Material(BaseModel):
    """货物清单行项目。"""
    sub_no: str = ""
    pkg: str = ""
    project: str = ""
    desc: str = ""
    unit: str = ""
    qty: str = ""
    deliver_date: str = ""
    deliver_place: str = ""
    spec_id: str = ""


class QualificationItem(BaseModel):
    sub_name: str = ""
    pkg: str = ""
    performance_req: str = ""
    test_report_req: str = ""
    other_reqs: Dict[str, str] = Field(default_factory=dict)
    accept_agent: str = ""


class PackageTRM(BaseModel):
    sub_no: str = ""
    sub_name: str = ""
    pkg_no: str = ""
    materials: List[Material] = Field(default_factory=list)
    qualification: List[QualificationItem] = Field(default_factory=list)
    spec_docs: List[SpecDoc] = Field(default_factory=list)


class TRM(BaseModel):
    batch_name: str = ""
    batch_no: str = ""
    terminology: str = "投标"      # 投标 | 应答
    source_zip: str = ""
    prenotice: List[PrenoticeClause] = Field(default_factory=list)
    rejection_rules: List[RejectionRule] = Field(default_factory=list)
    submission_table: List[SubmissionItem] = Field(default_factory=list)
    packages: List[PackageTRM] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "批次: {} ({})".format(self.batch_name or "?", self.batch_no or "?"),
            "术语体系: {}".format(self.terminology),
            "前附表条款: {} 条".format(len(self.prenotice)),
            "否决规则: {} 条".format(len(self.rejection_rules)),
            "提交方式表: {} 项".format(len(self.submission_table)),
            "标包: {} 个".format(len(self.packages)),
        ]
        for p in self.packages:
            n_star = sum(1 for s in p.spec_docs for r in s.param_rows if r.star)
            n_rows = sum(len(s.param_rows) for s in p.spec_docs)
            lines.append(
                "  - {} {} {} | 清单行 {} | 规范书 {} 本 | 参数行 {}（★{}）".format(
                    p.sub_no, p.sub_name, p.pkg_no,
                    len(p.materials), len(p.spec_docs), n_rows, n_star))
        if self.warnings:
            lines.append("警告: " + "; ".join(self.warnings))
        return "\n".join(lines)
