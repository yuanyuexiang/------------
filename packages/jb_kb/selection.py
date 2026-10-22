"""按包选择已审核资料；选择是生成输入的一部分，不修改企业知识库原件。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import CompanyProfile


class MaterialSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    certificates: Optional[list[str]] = None
    personnel: Optional[list[str]] = None
    performances: Optional[list[str]] = None
    financials: Optional[list[str]] = None
    products: Optional[list[str]] = None
    test_reports: Optional[list[str]] = None


def approved_profile(profile: CompanyProfile) -> CompanyProfile:
    result = profile.model_copy(deep=True)
    for kind in MaterialSelection.model_fields:
        setattr(result, kind, [x for x in getattr(result, kind) if x.status == "approved"])
    result.boilerplates = [x for x in result.boilerplates if x.approved]
    return result


def select_profile(profile: CompanyProfile, selection: Optional[MaterialSelection] = None) -> CompanyProfile:
    result = approved_profile(profile)
    selection = selection or MaterialSelection()
    for kind in MaterialSelection.model_fields:
        ids = getattr(selection, kind)
        if ids is None:
            continue
        if len(ids) != len(set(ids)):
            raise ValueError(f"{kind} 不能重复选择")
        items = {x.id: x for x in getattr(result, kind)}
        if any(not key or key not in items for key in ids):
            raise ValueError(f"{kind} 包含不属于本企业或未审核的资料，请重新选材")
        setattr(result, kind, [items[key] for key in ids])
    if selection.personnel is None:
        result.personnel = [p for p in result.personnel if p.available is not False]
    # 未指定年份时采用最近三个已审核年度；比较列不能冒充独立审计。
    if selection.financials is None:
        result.financials = sorted([f for f in result.financials if f.report_kind == "independent"], key=lambda f: f.year, reverse=True)[:3]
    return result


def certificate_validity(certificate) -> str:
    kind = getattr(certificate, "validity_kind", "dated")
    if kind == "permanent":
        return "长期"
    if kind == "point_in_time":
        return f"查询/出具日期 {certificate.valid_from}（时点材料）" if certificate.valid_from else ""
    return f"有效期至 {certificate.valid_until}" if certificate.valid_until else ""
