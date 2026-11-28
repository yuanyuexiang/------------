"""Extract explicitly labelled company facts from originals already in the knowledge base."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from lxml.etree import XMLSyntaxError

from . import attachments, company_sources
from .models import Attachment, CompanyProfile, EvidenceOrigin
from .text_evidence import read_evidence, registry_ocr

KINDS = ("registry", "credit", "certificate", "contract", "award", "financial", "test_report")
MAX_ORIGINAL_BYTES = 30_000_000
ORIGINAL_TYPES = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".tif": "image/tiff", ".tiff": "image/tiff", ".webp": "image/webp",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_CREDIT_TITLES = {
    "信用中国": ("信用中国", "creditchina.gov.cn"),
    "国家企业信用信息公示系统": ("国家企业信用信息公示系统", "gsxt.gov.cn"),
    "中国裁判文书网": ("中国裁判文书网", "wenshu.court.gov.cn"),
    "中国执行信息公开网": ("中国执行信息公开网", "zxgk.court.gov.cn"),
    "全国建筑市场监管公共服务平台": ("全国建筑市场监管公共服务平台", "jzsc.mohurd.gov.cn"),
    "国网供应商不良行为": ("供应商不良行为",),
}


def _word_text(path: str) -> dict:
    with ZipFile(path) as package:
        if sum(part.file_size for part in package.infolist()) > 80_000_000:
            raise ValueError("Word解包后过大")
    doc = Document(path)
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = list(dict.fromkeys(cell.text.strip().replace("\n", " ") for cell in row.cells))
            cells = [cell for cell in cells if cell]
            if len(cells) % 2 == 0:
                lines.extend(f"{cells[i]}：{cells[i + 1]}" for i in range(0, len(cells), 2))
            else:
                lines.append("  ".join(cells))
    text = "\n".join(lines)
    return {"pages": [{"page": None, "text": text[:90_000]}] if text else [],
            "notes": ["已读取 Word 文本和表格，内嵌扫描图片请用原始 PDF 或图片识别"]}


def _field(lines, labels, *, scanned=False):
    names = [r"\s*".join(map(re.escape, label)) if scanned else re.escape(label) for label in labels]
    separator = r"[ \t]+" if scanned else r"[ \t]{2,}"
    pattern = re.compile(rf"^\s*(?:{'|'.join(names)})(?:\s*[：:|]\s*|{separator})(.+?)\s*$")
    matches = {}
    for source, line in lines:
        match = pattern.match(line)
        if match:
            value = match.group(1).strip()
            if value:
                matches.setdefault(value, (source, line))
    if len(matches) == 1:
        value, (source, line) = next(iter(matches.items()))
        return value, source.model_copy(update={"excerpt": line[:500]})
    return "", None


def _registry(cp, lines, *, scanned=False):
    body = "\n".join(line for _, line in lines)
    normalized = re.sub(r"\s+", "", body) if scanned else body
    if "营业执照" not in normalized and "国家企业信用信息公示系统" not in normalized:
        return {}
    name, name_origin = _field(lines, ("名称", "企业名称", "市场主体名称"), scanned=scanned)
    if scanned:
        name = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", name)
    raw_code, code_origin = _field(lines, ("统一社会信用代码",), scanned=scanned)
    if scanned and not raw_code:
        candidates = {}
        for (_, label), (source, following) in zip(lines, lines[1:]):
            if re.sub(r"\s+", "", label) == "统一社会信用代码":
                codes = re.findall(r"(?<![A-Z0-9])[A-Z0-9]{18}(?![A-Z0-9])", following.upper())
                if len(codes) == 1:
                    candidates[codes[0]] = source.model_copy(
                        update={"excerpt": f"统一社会信用代码 {following}"[:500]}
                    )
        if len(candidates) == 1:
            raw_code, code_origin = next(iter(candidates.items()))
    try:
        code = company_sources.credit_code(re.sub(r"\s+", "", raw_code) if scanned else raw_code)
    except ValueError:
        return {}
    if not name or len(name) > 128:
        return {}
    if cp and (name != cp.name or (cp.credit_code and code != cp.credit_code.strip().upper())):
        return {}
    found = {"name": (name, name_origin), "credit_code": (code, code_origin)}
    for field, labels in (
        ("legal_person", ("法定代表人",)),
        ("address", ("住所", "注册地址")),
        ("business_scope", ("经营范围",)),
        ("founded", ("成立日期", "成立时间")),
        ("company_type", ("类型", "企业类型", "主体类型")),
        ("registered_capital_wan", ("注册资本",)),
    ):
        value, origin = _field(lines, labels, scanned=scanned)
        if field == "founded":
            value = company_sources.exact_date(value)
        elif field == "business_scope" and scanned and len(value) < 10:
            value = ""
        elif field == "registered_capital_wan":
            # Chinese registration originals may also report capital denominated in a foreign currency.
            value = company_sources.amount_in_rmb(value) if "人民币" in value else None
            if value is not None and value < 0:
                value = None
        if origin and value is not None and value != "":
            found[field] = (value, origin)
    return found


def _registry_with_ocr(path, cp, lines, filename, attachment_id, pages):
    fields = _registry(cp, lines)
    if fields or Path(path).suffix.lower() == ".docx" or (
        pages and all(page.get("method") == "text" for page in pages)
    ):
        return fields, lines
    source = EvidenceOrigin(kind="attachment", title=filename, attachment_id=attachment_id,
                            fetched_at=datetime.now(timezone.utc).isoformat(), page=1)
    attempts = registry_ocr(path)
    try:
        for text in attempts:
            scanned = [(source, line) for line in text.splitlines() if line.strip()]
            if fields := _registry(cp, scanned, scanned=True):
                return fields, scanned
    finally:
        attempts.close()
    return {}, lines


def _origin_for(fields):
    return next(source for _, source in fields.values())


def _record(kind, title, fields, **extra):
    return {"kind": kind, "title": title,
            "data": {**{key: value for key, (value, _) in fields.items()}, **extra},
            "origin": _origin_for(fields),
            "field_origins": {key: source for key, (_, source) in fields.items()}}


def _records(kind, lines, body, filename):
    def fields_for(labels, dates=()):
        result = {}
        for key, labels_for_field in labels.items():
            value, source = _field(lines, labels_for_field)
            value = company_sources.exact_date(value) if key in dates else value
            if value and source:
                result[key] = (value[:255], source)
        return result

    if kind == "credit":
        sites = [label for label, words in _CREDIT_TITLES.items() if any(word in body for word in words)]
        cover = _credit_cover(lines)
        if cover:
            sites, lines = ["信用中国"], cover
        values = fields_for({"valid_from": ("报告生成日期", "查询日期", "报告日期", "出具日期", "查询时间")}, ("valid_from",))
        if len(sites) == 1 and values:
            label = sites[0]
            return [_record("certificates", label + "查询材料", values,
                            name=label + "查询材料", issuer=label, cert_type="信用查询",
                            validity_kind="point_in_time")]
    if kind == "certificate":
        values = fields_for({
            "name": ("证书名称", "资质名称"), "number": ("证书编号", "证书号", "许可证编号"),
            "issuer": ("发证机关", "发证机构", "认证机构"),
            "valid_from": ("颁发日期", "发证日期", "有效期自"),
            "valid_until": ("有效期至", "有效期截止日", "证书有效期至"),
        }, ("valid_from", "valid_until"))
        if "number" in values:
            return [_record("certificates", values.get("name", (filename,))[0], values,
                            name=values.get("name", (filename,))[0])]
    if kind == "contract" and "合同" in body:
        values = fields_for({
            "project": ("项目名称", "合同名称"), "buyer": ("甲方", "甲方名称", "买方", "采购人"),
            "signed_date": ("合同签订日期", "合同签署日期", "签订日期", "签署日期"),
            "service_scope": ("服务范围", "合同范围"),
        }, ("signed_date",))
        value, source = _field(lines, ("合同金额", "合同总额", "合同总价"))
        amount = company_sources.amount_in_rmb(value)
        if source and amount is not None and amount >= 0:
            values["amount_wan"] = (amount, source)
        if "project" in values:
            return [_record("performances", values["project"][0], values, evidence=["合同"])]
    if kind == "award" and re.search("中标公告|成交结果|中标结果", body) and "候选人公示" not in body:
        values = fields_for({
            "project": ("项目名称", "采购项目名称"), "buyer": ("采购人", "招标人"),
            "award_date": ("公告日期", "发布日期", "中标日期"),
            "award_project_no": ("项目编号", "采购项目编号"),
        }, ("award_date",))
        value, source = _field(lines, ("中标金额", "成交金额", "中标成交金额"))
        amount = company_sources.amount_in_rmb(value)
        if source and amount is not None and amount >= 0:
            values["award_amount_wan"] = (amount, source)
        if "project" in values:
            return [_record("performances", values["project"][0], values)]
    if kind == "financial":
        values = fields_for({"year": ("会计年度", "报告年度", "审计年度")})
        if values and re.fullmatch(r"(?:19|20)\d{2}年?", values["year"][0]):
            for key, label in (("revenue_wan", "营业收入"), ("net_profit_wan", "净利润"),
                               ("asset_wan", "资产总额"), ("liability_wan", "负债总额")):
                value, source = _field(lines, (label,))
                amount = company_sources.amount_in_rmb(value)
                if source and amount is not None:
                    values[key] = (amount, source)
            # An extracted summary remains attached to its source as a draft for report-scope review.
            if len(values) > 1:
                independent = "审计报告" in body and "审计意见" in body
                return [_record("financials", values["year"][0] + " 财务资料", values,
                                report_kind="independent" if independent else "comparative")]
    if kind == "test_report":
        values = fields_for({
            "name": ("报告名称", "检验项目"), "number": ("报告编号", "检测报告编号", "报告号"),
            "agency": ("检测机构", "检验机构", "试验机构"),
            "issued_date": ("签发日期", "报告日期", "出具日期"),
            "valid_until": ("有效期至",),
        }, ("issued_date", "valid_until"))
        model, source = _field(lines, ("规格型号", "产品型号", "样品型号"))
        if model and source and re.fullmatch(r"[A-Za-z0-9.·_/-]{1,100}", model):
            values["covered_models"] = ([model], source)
        if "number" in values:
            return [_record("test_reports", values.get("name", (filename,))[0], values,
                            name=values.get("name", (filename,))[0])]
    return []


def _credit_cover(lines):
    cover = [(source, line) for source, line in lines if source.page in (None, 1)]
    text = "".join(line for _, line in cover)
    return cover if "公共信用信息报告" in text and "国家公共信用和地理空间信息中心" in text else []


def extract(cp: CompanyProfile, attachment: Attachment, kind: str) -> dict:
    if attachment.size > MAX_ORIGINAL_BYTES:
        raise ValueError("此文件超过30 MB，请选取包含关键信息的原件页上传")
    return extract_original(attachments.absolute_path(attachment), attachment.filename, kind, cp,
                            attachment.id)


def extract_original(path: str, filename: str, kind: str, cp: Optional[CompanyProfile],
                     attachment_id: str = "") -> dict:
    try:
        result = _word_text(path) if Path(path).suffix.lower() == ".docx" else read_evidence(path, ocr_pages=3)
    except (OSError, BadZipFile, PackageNotFoundError, XMLSyntaxError, ValueError):
        result = {"pages": [], "notes": ["文件读取未完成，请查看原件"]}
    lines = []
    for page in result["pages"]:
        origin = EvidenceOrigin(
            kind="attachment", title=filename,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            attachment_id=attachment_id, page=page["page"],
        )
        lines.extend((origin, line) for line in page["text"].splitlines())
    body = "\n".join(line for _, line in lines)
    fields, records = {}, []
    if kind == "registry":
        fields, registry_lines = _registry_with_ocr(
            path, cp, lines, filename, attachment_id, result["pages"]
        )
        if fields and any(re.sub(r"\s+", "", line) in ("营业执照", "电子营业执照")
                          for _, line in registry_lines):
            value, origin = fields["credit_code"]
            records = [_record("certificates", "营业执照", {"number": (value, origin)},
                               name="营业执照", cert_type="营业执照")]
    elif cp is not None:
        labels = {
            "contract": ("乙方", "乙方名称", "卖方", "供应商"),
            "award": ("中标供应商名称", "成交供应商名称", "中标单位", "中标成交供应商名称"),
        }
        label = labels.get(kind, (
            "企业名称", "单位名称", "信用主体名称", "主体名称", "机构名称", "编制单位", "被审计单位",
            "申请单位", "获证组织", "制造商", "生产单位", "委托单位", "受检单位",
        ))
        identity_lines = (_credit_cover(lines) or lines) if kind == "credit" else lines
        named, _ = _field(identity_lines, label)
        code, _ = _field(identity_lines, ("统一社会信用代码", "统一信用代码"))
        valid = named == cp.name or kind not in labels and cp.credit_code and code == cp.credit_code
        if valid and (not named or named == cp.name) and (not code or not cp.credit_code or code == cp.credit_code):
            records = _records(kind, lines, body, filename)
    status = "待核对" if fields or records else "需查看原件"
    detail = "已提取可核对的字段" if fields or records else "当前页未取得可唯一匹配的主体和字段"
    return {"fields": fields, "records": records,
            "checks": [{"title": filename, "status": status,
                        "detail": "。".join([detail, *result["notes"]])}]}
