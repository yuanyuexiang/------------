"""Turn the current package's parsed clauses into actions for obtaining original evidence."""
from __future__ import annotations

import re

from jb_kb.credit import credit_materials, grid_credit_requirement
from jb_kb.online import CNCA, CREDIT_CHINA, ECP, GSXT, NEA, PROCUREMENT

_CREDIT = (
    ("信用中国", ("信用中国", "creditchina.gov.cn"), CREDIT_CHINA),
    ("国家企业信用信息公示系统", ("国家企业信用信息公示", "gsxt.gov.cn"), GSXT),
    ("中国裁判文书网", ("裁判文书网", "wenshu.court.gov.cn"), "https://wenshu.court.gov.cn/"),
    ("中国执行信息公开网", ("执行信息公开网", "zxgk.court.gov.cn"), "https://zxgk.court.gov.cn/"),
    ("全国建筑市场监管公共服务平台", ("建筑市场监管",), "https://jzsc.mohurd.gov.cn/"),
)

_ORIGINALS = (
    ("营业执照", r"营业执照|事业单位法人证书", ("certificates",), GSXT, "核对主体及执照副本"),
    ("资质证照", r"资质条件|管理体系认证|许可证|资质证书|CCC|ISO\s*\d", ("certificates",),
     CNCA, "核对证书主体、范围、有效状态及有效期"),
    ("业绩证明", r"业绩要求|类似业绩|销售业绩|业绩证明|合同.{0,40}发票",
     ("performances",), PROCUREMENT, "核对招标指定的合同、发票、验收或投运证明"),
    ("人员证明", r"主要人员|项目负责人|社会保险|社保证明|劳动合同|项目团队",
     ("personnel",), "", "核对本次团队、人员证书、社保月份及缴纳主体"),
    ("财务材料", r"审计报告|经审计|财务报表|财务状况|资产负债表",
     ("financials",), "", "核对要求的年度、审计报告和报表"),
    ("检测和技术证明", r"检测报告|型式试验|试验报告|检验报告|鉴定报告",
     ("test_reports", "certificates"), "", "核对报告覆盖型号、试验范围和出具日期"),
    ("本次授权", r"授权委托书|法定代表人授权|法定代表人身份证明|授权代表",
     (), "", "确认本次签署人、授权范围和所需附件"),
)
_PERFORMANCE_PROOFS = ("合同", "发票", "验收", "投运")


def _rows_matching(rows, expression):
    return [row for row in rows if row["group"] != "specification"
            and re.search(expression, f'{row["title"]}\n{row["text"]}')]


def _entry(title, rows, tab, url, status, note, source_label="查看官方入口"):
    return {"title": title, "status": status, "note": note, "tab": tab,
            "url": url, "source_label": source_label,
            "clauses": [{"id": row["id"], "source": row["source"], "title": row["title"]}
                        for row in rows]}


def _has_original(records, kind, item):
    return bool(records.get(f"{kind}:{item.id}", {}).get("attachments"))


def _relevant_item(title, item):
    if title == "营业执照":
        return bool(re.search(r"营业执照|事业单位法人证书", item.name))
    if title == "资质证照":
        return bool(re.search(r"资质|认证|许可|\bISO|\bCCC|管理体系", item.name + item.cert_type))
    if title == "检测和技术证明":
        return bool(re.search(r"检测|试验|检验|鉴定", item.name))
    return True


def checks(rows, trm, package, chosen, records, authorization_confirmed):
    result = []
    credit = credit_materials(chosen)
    for title, words, url in _CREDIT:
        sources = _rows_matching(rows, "|".join(re.escape(word) for word in words))
        if sources:
            linked = any(_has_original(records, "certificates", item) for item in credit[title])
            status = "已有材料，核对时效" if linked else "待核对查询材料"
            result.append(_entry(title, sources, "certificates", url, status, "查看本包原文及指定报告格式"))

    grid = grid_credit_requirement(trm, package)
    if grid["mode"] != "unspecified":
        sources = _rows_matching(rows, r"不良行为")
        linked = any(_has_original(records, "certificates", item) for item in credit["国网供应商不良行为"])
        label, note = {
            "buyer": ("采购方核查", "本包条款指明由采购方或评审方核验"),
            "exempt": ("按原文免交", "本包条款指明无须提交查询附件"),
            "condition": ("核对本包资格限制", "按本包规定核对不良行为处理范围"),
            "declaration": ("待核对声明", "核实本企业情况后审阅本包承诺或声明"),
            "conflict": ("提交要求待核对", "原文存在提交与免交的不同表述"),
            "evidence": ("已有材料，核对时效" if linked else "待补查询凭证", "按本包原文取得查询凭证"),
        }[grid["mode"]]
        result.append(_entry("国网供应商不良行为", sources, "certificates", ECP, label, note))

    for title, expression, kinds, url, note in _ORIGINALS:
        sources = _rows_matching(rows, expression)
        if not sources:
            continue
        items = [item for kind in kinds for item in getattr(chosen, kind)
                 if _relevant_item(title, item) and _has_original(records, kind, item)]
        status = "有已选原件，待核对" if items else "待补或选用原件"
        if title == "本次授权":
            status = "已确认安排，核对原件" if authorization_confirmed else "待确认本次授权"
        if title == "业绩证明":
            explicit = [label for label in _PERFORMANCE_PROOFS
                        if any(row["group"] == "qualification" and label in row["text"] for row in sources)]
            if explicit:
                proof = [set(item.evidence) for item in items]
                absent = [label for label in explicit if not any(
                    any(label in kind for kind in kinds_in_item) for kinds_in_item in proof)]
                if absent:
                    status = "待核对：" + "、".join(absent)
        if title == "资质证照" and any(re.search(r"承装|承修|承试", row["text"]) for row in sources):
            url = NEA
        result.append(_entry(title, sources, kinds[0] if kinds else "attachments", url, status, note))
    return result
