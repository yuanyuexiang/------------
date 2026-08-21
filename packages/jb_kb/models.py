"""jb-kb：企业知识库数据模型（S2 落 PostgreSQL 前的 Pydantic 定义 + JSON 存取）。

原则（见 CLAUDE.md）：事实字段只能来自结构化数据；每条记录尽量带 source（出处）。
"""
from __future__ import annotations

import json
import os
from typing import Optional

from pydantic import BaseModel, Field


class Certificate(BaseModel):
    name: str = ""              # 如"质量管理体系认证证书"
    cert_type: str = ""         # 体系认证/资质等级/许可证/信用等级/...
    number: str = ""
    issuer: str = ""
    valid_until: str = ""       # YYYY-MM-DD；空=未录入（不猜）
    source: str = ""


class Person(BaseModel):
    name: str = ""
    title: str = ""             # 职务/职称
    major: str = ""
    credentials: list[str] = Field(default_factory=list)  # 身份证/学历证/职称证书/社保证明/劳动合同…
    source: str = ""


class Performance(BaseModel):
    project: str = ""
    buyer: str = ""
    buyer_is_end_user: Optional[bool] = None   # 国网业绩认定关键字段；未知留 None
    amount_wan: Optional[float] = None
    signed_date: str = ""
    evidence: list[str] = Field(default_factory=list)     # 合同/发票/中标通知书…
    source: str = ""


class FinancialYear(BaseModel):
    year: str = ""
    revenue_wan: Optional[float] = None
    net_profit_wan: Optional[float] = None
    asset_wan: Optional[float] = None
    liability_ratio: str = ""


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
    sources: list[str] = Field(default_factory=list)      # 建档依据文件

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: str) -> CompanyProfile:
        with open(path, encoding="utf-8") as f:
            return cls.model_validate(json.load(f))
