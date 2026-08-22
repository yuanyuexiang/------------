"""jb-kb：企业知识库数据模型（S2 落 PostgreSQL 前的 Pydantic 定义 + JSON 存取）。

原则（见 CLAUDE.md）：事实字段只能来自结构化数据；每条记录尽量带 source（出处）。
"""
from __future__ import annotations

import json
import os
from typing import Optional

from pydantic import BaseModel, Field


# 知识库条目通用字段（P2 拆表后每条记录独立成行）：
#   id           落库后的行 ID；建档/导入阶段为空，入库时分配
#   status       draft（待审核）| approved（审核生效）——只有 approved 的事实才进投标文件
#   attachments  扫描件附件 ID 列表（见 Attachment）
class Certificate(BaseModel):
    id: str = ""
    name: str = ""              # 如"质量管理体系认证证书"
    cert_type: str = ""         # 体系认证/资质等级/许可证/信用等级/...
    number: str = ""
    issuer: str = ""
    level: str = ""             # 等级（如 AAA / 二级）
    valid_from: str = ""        # YYYY-MM-DD
    valid_until: str = ""       # YYYY-MM-DD；空=未录入（不猜）
    status: str = "approved"
    attachments: list[str] = Field(default_factory=list)
    source: str = ""


class Person(BaseModel):
    id: str = ""
    name: str = ""
    title: str = ""             # 职务/职称
    major: str = ""
    education: str = ""         # 学历
    social_insurance_unit: str = ""   # 社保缴纳单位（须与投标人一致）
    available: Optional[bool] = None  # 可投入状态；None=未录入
    credentials: list[str] = Field(default_factory=list)  # 身份证/学历证/职称证书/社保证明/劳动合同…
    status: str = "approved"
    attachments: list[str] = Field(default_factory=list)
    source: str = ""


class Performance(BaseModel):
    id: str = ""
    project: str = ""
    buyer: str = ""
    buyer_type: str = ""        # 国网单位/其他电力/非电力…
    buyer_is_end_user: Optional[bool] = None   # 国网业绩认定关键字段；未知留 None
    in_sgcc: Optional[bool] = None             # 国网系统内业绩
    amount_wan: Optional[float] = None
    signed_date: str = ""
    commissioned_date: str = ""                # 投运/验收日期
    material_category: str = ""                # 物料类别
    voltage_level: str = ""
    evidence: list[str] = Field(default_factory=list)     # 合同/发票/中标通知书…
    status: str = "approved"
    attachments: list[str] = Field(default_factory=list)
    source: str = ""


class FinancialYear(BaseModel):
    id: str = ""
    year: str = ""
    revenue_wan: Optional[float] = None
    net_profit_wan: Optional[float] = None
    asset_wan: Optional[float] = None
    liability_ratio: str = ""
    status: str = "approved"
    attachments: list[str] = Field(default_factory=list)   # 审计报告扫描件
    source: str = ""


class Product(BaseModel):
    """产品（物资类技术参数响应的数据源）。params 的 key 为参数名/关键词，value 为具体值字符串。"""
    id: str = ""
    model: str = ""                 # 型号
    name: str = ""                  # 名称/物料类别
    category: str = ""
    params: dict[str, str] = Field(default_factory=dict)   # {"CPU": "2*32Core@2.6GHz", "内存": "256GB", ...}
    features: list[str] = Field(default_factory=list)      # 功能描述（供描述性要求匹配）
    test_reports: list[str] = Field(default_factory=list)  # 关联检测报告名
    spec_ids: list[str] = Field(default_factory=list)      # 适配的技术规范 ID
    status: str = "approved"
    attachments: list[str] = Field(default_factory=list)
    source: str = ""


class TestReport(BaseModel):
    """检测/型式试验/鉴定报告：资格条件常要求"报告在有效期内"，有效期按开标日推算。"""
    id: str = ""
    name: str = ""
    report_type: str = ""           # 型式试验 / 检测 / 鉴定
    agency: str = ""
    number: str = ""
    issued_date: str = ""           # YYYY-MM-DD
    valid_until: str = ""           # YYYY-MM-DD；空=按招标文件规则推算或未录入
    covered_models: list[str] = Field(default_factory=list)
    status: str = "approved"
    attachments: list[str] = Field(default_factory=list)
    source: str = ""


class Boilerplate(BaseModel):
    """审核过的话术段落（售后/质量/培训等），写作 Agent 的素材；非事实内容可复用。"""
    id: str = ""
    topic: str = ""                 # 售后服务 / 质量保证 / 培训 / 保密 / 应急...
    title: str = ""
    text: str = ""
    applicable_types: list[str] = Field(default_factory=list)   # 适用：物资/服务/…；空=通用
    source: str = ""
    approved: bool = False


class Attachment(BaseModel):
    """扫描件/证明文件（对象存储元数据；文件本体在 UPLOAD_DIR/attachments 或 MinIO）。"""
    id: str = ""
    kind: str = ""                  # certificate / person / performance / financial / product / test_report / other
    filename: str = ""
    content_type: str = ""
    size: int = 0
    sha256: str = ""
    storage_path: str = ""
    uploaded_at: str = ""


class CompanyProfile(BaseModel):
    name: str = ""
    credit_code: str = ""
    legal_or_admin: str = ""        # 行政/技术负责人（样本口径）
    founded: str = ""
    registered_capital_wan: Optional[float] = None
    company_type: str = ""
    address: str = ""
    bank: str = ""
    contact: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    staff_total: Optional[int] = None
    staff_technical: Optional[int] = None
    senior_engineers: Optional[int] = None
    engineers: Optional[int] = None
    business_scope: str = ""
    certificates: list[Certificate] = Field(default_factory=list)
    personnel: list[Person] = Field(default_factory=list)
    performances: list[Performance] = Field(default_factory=list)
    financials: list[FinancialYear] = Field(default_factory=list)
    products: list[Product] = Field(default_factory=list)
    test_reports: list[TestReport] = Field(default_factory=list)
    boilerplates: list[Boilerplate] = Field(default_factory=list)
    legal_person: str = ""          # 法定代表人
    authorized_rep: str = ""        # 常用被授权人
    authorized_rep_title: str = ""
    sources: list[str] = Field(default_factory=list)      # 建档依据文件

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: str) -> CompanyProfile:
        with open(path, encoding="utf-8") as f:
            return cls.model_validate(json.load(f))
