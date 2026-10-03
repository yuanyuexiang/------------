"""母版驱动装配：在招标文件"文件格式"章的商务段/技术段切片上原位填空，产出与国网格式一致的投标文件。

与 builder（自建版式）的分工：本模块只在"母版可用"时装配；某一段找不到或装配异常，generate()
退回 builder 自建版式并写入 notes。事实字段仍只来自档案/TRM，缺失写【待补充】（导出阻断不变）。

填充策略（对应 docs/国网真实招标文件结构分析.md §3.3/§6 的实测版式）：
- 段落：第六章原文 pattern（builder.fill_blanks）+ "标签：" 行补值（master.label_subs），跨 run 先合并；
- 表格：标签|值 式表（基本情况表）按标签填右格；清单式表（偏差/业绩/人员/认证/技术参数）按表头关键词映射列，
  不够的行克隆模板行；多本规范书时整表克隆；
- 扫描件：按格式块标题锚点插图（知识库附件），无图写【待补充】；写作 Agent 草稿与话术插到对应标题后。
"""
from __future__ import annotations

import copy
import os
import re
from typing import Optional

from docx.table import Table

from . import master as M
from .builder import GenContext, append_spec_responses, fill_blanks, iter_markdown
from .placeholders import todo
from .scans import images_for
from .techparams import TechParamResult, deviation_rows, fill_spec
from .techparams import star_text as _star

_ANY = re.compile(r"^[\s\S]+$")


def _s(v) -> str:
    return "" if v is None else str(v)


def _wan(v) -> str:
    if v is None:
        return ""
    num = int(v) if isinstance(v, float) and v.is_integer() else v
    return f"{num}万元"


# ---------- 段落填空 ----------

def _labels(ctx: GenContext) -> dict[str, str]:
    k, p, b = ctx.profile, ctx.pkg, ctx.trm
    proj = p.project_name or b.batch_name
    raw = {
        "投标人名称": k.name, "应答人名称": k.name, "投标人": k.name, "应答人": k.name, "单位名称": k.name,
        "地址": k.address, "单位地址": k.address, "注册地址": k.address,
        "电话": k.phone, "联系电话": k.phone, "联系人": k.contact, "网址": k.website,
        "授权代表姓名": k.authorized_rep, "授权代表职务": k.authorized_rep_title,
        "法定代表人（单位负责人）或授权代表": k.authorized_rep or k.legal_person,
        "项目名称": proj, "项目编号": b.batch_no, "招标编号": b.batch_no, "采购编号": b.batch_no,
        "项目单位": p.project_unit,
        "分标编号": p.sub_no, "分标": p.sub_no, "分标名称": p.sub_name, "货物类别": p.sub_name,
        "包号": p.pkg_no, "包名称": p.pkg_no, "分包编号": p.pkg_no, "分包": p.pkg_no,
        "员工总人数": _s(k.staff_total), "统一社会信用代码": k.credit_code,
    }
    return {key: v for key, v in raw.items() if v}


def _subs(ctx: GenContext) -> list:
    return [(_ANY, lambda m: fill_blanks(m.group(0), ctx))] + M.label_subs(_labels(ctx))


# ---------- 扫描件 ----------

def _insert_scans(ctx: GenContext, doc, anchor_el, ids: list[str], what: str):
    """锚点后依次插入附件图片；没有任何可插图片时写【待补充】。返回新锚点。"""
    last = anchor_el
    for aid in ids:
        images, reason = images_for(ctx.attachment_paths.get(aid, ""))
        ok = 0
        for img in images:
            para = M.insert_picture_after(doc, last, img)
            if para is not None:
                last, ok = para._p, ok + 1
        if not ok:
            last = M.insert_paragraph_after(doc, last, todo(f"{what}（{reason or '图片插入失败'}）"))._p
    if not ids:
        last = M.insert_paragraph_after(doc, last, todo(f"{what}扫描件插入"))._p
    return last


def _cover(ctx: GenContext, kind: str) -> list[tuple[str, bool]]:
    p, b = ctx.pkg, ctx.trm
    return [
        ("投标文件" if b.terminology == "投标" else "应答文件", True),
        (f"（{kind}）", True),
        (f"项目名称：{ctx.need(p.project_name or b.batch_name, '项目名称')}", False),
        (f"招标编号：{ctx.need(b.batch_no, '招标编号')}", False),
        (f"分标/包：{p.sub_no} {p.sub_name} {p.pkg_no}".strip(), False),
        (f"投标人：{ctx.need(ctx.profile.name, '投标人名称')}", False),
        ("法定代表人（单位负责人）或其授权代表人：　　　　（签字）", False),
    ]


# ---------- 商务文件 ----------

def _fill_basic_info(doc, ctx: GenContext) -> None:
    k = ctx.profile
    t = M.find_table(doc, ["投标人名称", "应答人名称", "单位名称", "注册地址", "统一社会信用代码", "成立时间"], min_hits=2)
    if t is None:
        return
    cap = _wan(k.registered_capital_wan)
    M.set_kv_cells(t, {
        "投标人名称": k.name, "应答人名称": k.name, "单位名称": k.name,
        "注册地址": k.address, "单位地址及邮编": k.address, "单位地址": k.address,
        "联系人": k.contact, "电话": k.phone, "网址": k.website,
        "成立时间": k.founded, "统一社会信用代码": k.credit_code,
        "注册资金": cap, "注册资本": cap, "开户银行": k.bank, "经营范围": k.business_scope,
        "高级职称人员": _s(k.senior_engineers), "中级职称人员": _s(k.engineers),
        "法定代表人（单位负责人）": k.legal_person, "法定代表人": k.legal_person, "技术负责人": k.legal_or_admin,
    }, row_scoped={"法定代表人": {"姓名": k.legal_person}, "技术负责人": {"姓名": k.legal_or_admin}})


def _fill_financials(doc, ctx: GenContext) -> Optional[Table]:
    t = M.find_table(doc, ["财务指标"], min_hits=1)
    fins = sorted(ctx.profile.financials, key=lambda f: f.year, reverse=True)
    if t is None or not fins:
        return t
    cols = M.cells_by_grid(t.rows[0])
    year_cols = [c for c, cell in sorted(cols.items()) if re.fullmatch(r"X+年?|\d{4}年?", M.norm(cell.text))]
    pairs = list(zip(year_cols, fins))
    for col, f in pairs:
        M.set_cell_text(cols[col], f"{f.year}年")
    cap = ctx.profile.registered_capital_wan
    getters = [("资产负债率", lambda f: f.liability_ratio), ("资产总额", lambda f: _wan(f.asset_wan)),
               ("营业收入", lambda f: _wan(f.revenue_wan)), ("净利润", lambda f: _wan(f.net_profit_wan)),
               ("注册资本", lambda f: _wan(cap))]
    for row in t.rows[1:]:
        cells = M.distinct_cells(row)
        name = M.norm(cells[1].text if len(cells) > 1 else cells[0].text)
        getter = next((g for kw, g in getters if name.startswith(kw)), None)
        if getter is None:
            continue
        grid = M.cells_by_grid(row)
        for col, f in pairs:
            cell = grid.get(col)
            v = getter(f)
            if cell is not None and v and not cell.text.strip():
                M.set_cell_text(cell, str(v))
    return t


def _cert_section(ctx: GenContext, doc, anchor_el, title: str, certs: list):
    last = M.insert_heading_after(doc, anchor_el, title, level=3)._p
    if not certs:
        return M.insert_paragraph_after(doc, last, todo(f"{title}"))._p
    for c in certs:
        line = c.name + (f"（有效期至 {c.valid_until}）" if c.valid_until else f"（{todo(c.name + '有效期')}）")
        last = M.insert_paragraph_after(doc, last, line)._p
        last = _insert_scans(ctx, doc, last, c.attachments, c.name)
    return last


def build_commercial(ctx: GenContext, master_path: str, out_path: str) -> bool:
    doc = M.carve(master_path, "commercial")
    if doc is None:
        ctx.notes.append("母版未切出商务文件段，商务文件退回自建版式")
        return False
    k = ctx.profile
    M.remove_guidance(doc)
    M.fill_all(doc, _subs(ctx))
    _fill_basic_info(doc, ctx)

    t = M.find_table(doc, ["条目号", "条款", "偏差说明"])
    if t is not None:
        M.fill_by_header(t, [{"item": "/", "req": "/", "resp": "/", "note": "无偏差"}],
                         [("条目", "item"), ("招标文件条款|采购文件条款", "req"), ("投标文件条款|应答文件条款", "resp"),
                          ("偏差说明", "note")])

    t = M.find_table(doc, ["人员姓名", "身份证号", "与国网公司系统人员关系"])
    if t is not None:
        M.fill_by_header(t, [{"name": ctx.need(k.legal_person, "法定代表人姓名"), "sex": todo("性别"),
                              "idno": todo("法定代表人身份证号"), "post": "法定代表人",
                              "since": todo("任职时间"), "rel": "无"}],
                         [("人员姓名", "name"), ("性别", "sex"), ("身份证号", "idno"), ("职务", "post"),
                          ("任职时间", "since"), ("关系", "rel")])

    fin_tbl = _fill_financials(doc, ctx)
    if fin_tbl is not None:
        last = fin_tbl._tbl
        if k.financials:
            for f in sorted(k.financials, key=lambda x: x.year, reverse=True):
                last = M.insert_heading_after(doc, last, f"审计报告{f.year}年度", level=3)._p
                last = _insert_scans(ctx, doc, last, f.attachments, f"{f.year}年度审计报告")
        else:
            M.insert_paragraph_after(doc, last, todo("近三年财务审计报告"))

    biz = [c for c in k.certificates if "营业执照" in c.name]
    tax = [c for c in k.certificates if "税务" in c.name]
    system = [c for c in k.certificates if c.cert_type == "体系认证"]
    other = [c for c in k.certificates if c not in biz and c not in tax and c not in system]
    p = M.find_paragraph(doc, r"^(企业法人|企业)?营业执照", max_len=60)
    if p is not None:
        _insert_scans(ctx, doc, p._p, [a for c in biz for a in c.attachments], "营业执照")
    p = M.find_paragraph(doc, r"^有效的税务登记证明", max_len=40)
    if p is not None:
        _insert_scans(ctx, doc, p._p, [a for c in tax for a in c.attachments], "税务登记证明")
    p = M.find_paragraph(doc, r"^(6\.1|\d\.\d)?符合.*资格要求的证明文件", max_len=60)
    if p is not None:
        last = _cert_section(ctx, doc, p._p, "企业资质等级证书", other)
        _cert_section(ctx, doc, last, "企业管理体系认证证书", system)
    p = M.find_paragraph(doc, r"查询报告及截图", max_len=40)
    if p is not None:
        last = p._p
        for item in ("信用中国（失信被执行人/严重失信主体）", "国家企业信用信息公示系统（经营异常/严重违法失信）",
                     "中国裁判文书网（行贿犯罪记录）"):
            last = M.insert_paragraph_after(doc, last, f"{item}：{todo(item + '查询截图')}")._p
    p = M.find_paragraph(doc, r"^基本账户证明", max_len=30)
    if p is not None:
        M.insert_paragraph_after(doc, p._p, todo("银行基本账户证明扫描件"))

    if not M.has_cover(doc):
        M.prepend_cover(doc, _cover(ctx, "商务文件"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    doc.save(out_path)
    return True


# ---------- 技术文件 ----------

_PARAM_COLS = [("名称|参数", "name"), ("单位", "unit"), ("要求值|需求值|表述", "req"), ("保证值|响应", "resp")]
_PARAM_HEADER = ["序号", "参数名称", "单位", "项目需求值或表述", "投标人保证值"]


def _param_records(sd, r: TechParamResult) -> list[dict]:
    return [{"name": row.name, "unit": row.unit, "req": _star(row),
             "resp": resp.response} for row, resp in zip(sd.param_rows, r.responses)]


def _fill_params(doc, ctx: GenContext, results: list[TechParamResult]):
    """填技术特性参数表；返回参数区最后一个元素（规范书逐条响应接在其后）。"""
    specs = list(zip(ctx.pkg.spec_docs, results))
    tpl = M.find_table(doc, ["要求值", "保证值"]) or M.find_table(doc, ["需求值", "保证值"])
    if tpl is None:
        p = M.find_paragraph(doc, r"技术特性参数表|技术参数")
        last = p._p if p is not None else M.last_body_element(doc)
        for sd, r in specs:
            last = M.insert_heading_after(doc, last, f"技术规范书 {sd.spec_id or sd.title}", level=2)._p
            if sd.param_rows:
                rows = [[str(i + 1), x["name"], x["unit"], x["req"], x["resp"]] for i, x in enumerate(_param_records(sd, r))]
                last = M.insert_table_after(doc, last, _PARAM_HEADER, rows)._tbl
            else:
                last = M.insert_paragraph_after(doc, last, todo(f"规范书 {sd.spec_id} 逐项响应（叙述式规范，见逐条响应章节）"))._p
        return last
    pristine = copy.deepcopy(tpl._tbl)
    last = tpl._tbl
    for i, (sd, r) in enumerate(specs):
        if i == 0:
            t = tpl
            prev = tpl._tbl.getprevious()
            if prev is not None and len(specs) > 1:
                M.insert_paragraph_after(doc, prev, f"技术规范书 {sd.spec_id or sd.title}", bold=True)
        else:
            last = M.insert_paragraph_after(doc, last, f"技术规范书 {sd.spec_id or sd.title}", bold=True)._p
            new = copy.deepcopy(pristine)
            last.addnext(new)
            t = Table(new, tpl._parent)
        last = t._tbl
        if sd.param_rows:
            if not M.fill_by_header(t, _param_records(sd, r), _PARAM_COLS):
                rows = [[str(j + 1), x["name"], x["unit"], x["req"], x["resp"]] for j, x in enumerate(_param_records(sd, r))]
                last = M.insert_table_after(doc, last, _PARAM_HEADER, rows, like=t)._tbl
        else:
            last = M.insert_paragraph_after(doc, last, todo(f"规范书 {sd.spec_id} 逐项响应（叙述式规范，见逐条响应章节）"))._p
    return last


def _fill_deviation(doc, results: list[TechParamResult]) -> None:
    rows = [x for r in results for x in deviation_rows(r)]
    recs = [{"clause": x["对应条款"], "req": x["招标文件要求"], "resp": x["投标响应"], "note": x["偏差说明"]} for x in rows] \
        or [{"clause": "/", "req": "/", "resp": "/", "note": "无偏差"}]
    colmap = [("偏差事项|对应条款|条款", "clause"), ("要求", "req"), ("响应", "resp"), ("偏差说明|说明", "note")]
    t = M.find_table(doc, ["偏差事项", "对应条款", "招标文件要求", "采购文件要求", "投标文件响应", "应答文件响应"])
    if t is not None and M.fill_by_header(t, recs, colmap):
        return
    p = M.find_paragraph(doc, r"技术偏差表")
    anchor = (t._tbl if t is not None else p._p if p is not None else M.last_body_element(doc))
    M.insert_table_after(doc, anchor, ["序号", "对应条款", "招标文件要求", "投标响应", "偏差说明"],
                         [[str(i + 1), x["clause"], x["req"], x["resp"], x["note"]] for i, x in enumerate(recs)], like=t)


def _fill_performances(doc, ctx: GenContext) -> None:
    k = ctx.profile
    model = ctx.product.model if ctx.product else ""
    recs = [{"model": model or x.material_category or None, "project": x.project, "buyer": x.buyer or todo("买方"),
             "amount": _wan(x.amount_wan) or todo("合同金额"), "done": x.commissioned_date or x.signed_date or todo("投运时间"),
             "signed": x.signed_date or todo("签约日期"), "voltage": x.voltage_level or None,
             "contact": todo(f"{x.project} 联系人及电话"), "evidence": "/".join(x.evidence), "remark": ""}
            for x in k.performances]
    colmap = [("产品型式|物料|产品名称|设备", "model"), ("工程名称|项目名称", "project"),
              ("项目单位|买方|采购人|用户|业主", "buyer"), ("金额|规模", "amount"), ("投运|验收|完成|交货", "done"),
              ("签约|签订|合同日期|合同时间", "signed"), ("电压", "voltage"), ("联系", "contact"),
              ("证明|支撑|附件", "evidence"), ("备注", "remark")]
    t = M.find_table(doc, ["工程名称", "投运时间", "产品型式"]) or M.find_table(doc, ["项目名称", "合同金额", "项目单位", "业绩"], min_hits=3)
    if t is not None and (not recs or M.fill_by_header(t, recs, colmap)):
        last = t._tbl
    else:
        p = M.find_paragraph(doc, r"业绩")
        last = M.insert_heading_after(doc, p._p if p is not None else M.last_body_element(doc), "供货及运行业绩表", level=2)._p
        last = M.insert_table_after(doc, last, ["序号", "项目名称", "买方", "签约时间", "金额（万元）", "证明材料"],
                                    [[str(i + 1), x["project"], x["buyer"], x["signed"], x["amount"], x["evidence"]]
                                     for i, x in enumerate(recs)], like=t)._tbl
    if not recs:
        M.insert_paragraph_after(doc, last, todo("业绩清单及合同/发票扫描件"))
        return
    for x in k.performances:
        last = M.insert_heading_after(doc, last, x.project, level=3)._p
        if x.attachments:
            last = _insert_scans(ctx, doc, last, x.attachments, f"{x.project} 业绩证明")
        else:
            for ev in x.evidence or ["合同", "发票"]:
                last = M.insert_paragraph_after(doc, last, f"{ev}：{todo(f'{x.project} 的{ev}扫描件')}")._p


def _fill_personnel(doc, ctx: GenContext) -> None:
    k = ctx.profile
    colmap = [("姓名", "name"), ("现担任职务|职务|职称", "title"), ("专业", "major"), ("学历", "education"),
              ("资格|证书|证明", "cred"), ("岗位|层级", "post"), ("工作经历|经历|年限", "exp"),
              ("通讯|电话|联系", "contact"), ("备注", "remark")]
    t = M.find_table(doc, ["岗位", "姓名", "职称", "层级", "现担任职务", "拟委任"])
    fields = M.header_fields(t, colmap) if t is not None else set()
    recs = []
    for x in k.personnel:
        title = x.title or todo(f"{x.name}职称")
        recs.append({"name": x.name, "title": title if "name" in fields else f"{x.name}（{title}）",
                     "major": x.major or None, "education": x.education or None, "post": None,
                     "cred": "、".join(x.credentials) or None, "exp": todo(f"{x.name} 工作经历"),
                     "contact": todo(f"{x.name} 联系方式"), "remark": ""})
    if t is not None and (not recs or M.fill_by_header(t, recs, colmap)):
        last = t._tbl
    else:
        p = M.find_paragraph(doc, r"技术人员|项目经理|项目团队|主要人员")
        last = M.insert_heading_after(doc, p._p if p is not None else M.last_body_element(doc), "主要技术人员", level=2)._p
        last = M.insert_table_after(doc, last, ["序号", "姓名", "职务/职称", "专业", "证件材料"],
                                    [[str(i + 1), x.name, x.title or todo(f"{x.name}职称"), x.major, "、".join(x.credentials)]
                                     for i, x in enumerate(k.personnel)], like=t)._tbl
    if not recs:
        M.insert_paragraph_after(doc, last, todo("拟投入人员清单及七件套材料"))
        return
    for x in k.personnel:
        last = M.insert_heading_after(doc, last, x.name, level=3)._p
        if x.attachments:
            last = _insert_scans(ctx, doc, last, x.attachments, f"{x.name} 证件材料")
        else:
            for c in (x.credentials or ["身份证", "学历证", "职称证书", "社保证明", "劳动合同"]):
                last = M.insert_paragraph_after(doc, last, f"{c}：{todo(f'{x.name} 的{c}扫描件')}")._p


def _fill_certs(doc, ctx: GenContext) -> None:
    k = ctx.profile
    certs = [c for c in k.certificates if c.cert_type == "体系认证"] or list(k.certificates)
    t = M.find_table(doc, ["信息事项", "认证机构", "证书编号", "认证事项"])
    if t is None:
        return
    recs = [{"name": c.name, "issuer": c.issuer or todo(f"{c.name}认证机构"), "number": c.number or todo(f"{c.name}证书编号"),
             "scope": None, "valid": c.valid_until or todo(f"{c.name}有效期"), "level": c.level or None} for c in certs]
    colmap = [("范围", "scope"), ("信息事项|证书名称|名称|认证事项", "name"), ("机构|发证", "issuer"), ("编号", "number"),
              ("有效期", "valid"), ("等级", "level")]
    if not recs:
        M.insert_paragraph_after(doc, t._tbl, todo("体系认证证书"))
        return
    M.fill_by_header(t, recs, colmap)
    last = t._tbl
    for c in certs:
        if c.attachments:
            last = M.insert_paragraph_after(doc, last, c.name)._p
            last = _insert_scans(ctx, doc, last, c.attachments, c.name)


def _insert_drafts(doc, ctx: GenContext) -> None:
    p = ctx.pkg
    if not ctx.drafts and not p.scope:
        return
    anchor = M.find_paragraph(doc, r"技术方案|服务方案|技术评分标准|评分标准.*支撑材料|需求响应")
    last = anchor._p if anchor is not None else M.last_body_element(doc)
    if anchor is None:
        last = M.insert_heading_after(doc, last, "技术/服务方案" if ctx.drafts else "项目需求响应", level=2)._p
    if p.scope:
        last = M.insert_paragraph_after(doc, last, "招标范围：" + p.scope)._p
    if not ctx.drafts:
        M.insert_paragraph_after(doc, last, todo("总体技术/服务方案（由写作 Agent 依据评分项起草）"))
        return
    has_bullet = M._style_or_none(doc, "List Bullet") is not None
    for sec in ctx.drafts:
        last = M.insert_heading_after(doc, last, sec.title, level=2)._p
        for kind, level, text in iter_markdown(sec.text):
            if kind == "h":
                last = M.insert_heading_after(doc, last, text, level=min(level + 1, 4))._p
            elif kind == "li":
                last = M.insert_paragraph_after(doc, last, text if has_bullet else "• " + text,
                                                style="List Bullet" if has_bullet else None)._p
            else:
                last = M.insert_paragraph_after(doc, last, text)._p


def _insert_boilerplates(doc, ctx: GenContext) -> None:
    for topic, pat, heading in (("售后服务", r"售后服务", "售后服务保障及承诺"), ("质量保证", r"质量保证", "质量保证措施方案"),
                                ("培训", r"技术服务|培训", "技术服务，包括培训、安装指导等")):
        anchor = M.find_paragraph(doc, pat, max_len=40)
        if anchor is None:
            continue
        last = anchor._p
        bps = [b for b in ctx.profile.boilerplates if b.topic == topic and b.approved]
        if not bps:
            M.insert_paragraph_after(doc, last, todo(f"{heading}（话术库暂无审核通过的段落）"))
            continue
        for b in bps:
            last = M.insert_paragraph_after(doc, last, b.text)._p


def build_technical(ctx: GenContext, master_path: str, out_path: str) -> tuple[bool, list[TechParamResult]]:
    doc = M.carve(master_path, "technical")
    if doc is None:
        ctx.notes.append("母版未切出技术文件段，技术文件退回自建版式")
        return False, []
    M.remove_guidance(doc)
    M.fill_all(doc, _subs(ctx))
    results = [fill_spec(sd, ctx.product) for sd in ctx.pkg.spec_docs]
    _fill_deviation(doc, results)
    last = _fill_params(doc, ctx, results)
    append_spec_responses(doc, last, ctx)
    _fill_performances(doc, ctx)
    _fill_personnel(doc, ctx)
    _fill_certs(doc, ctx)
    _insert_drafts(doc, ctx)
    _insert_boilerplates(doc, ctx)
    if not M.has_cover(doc):
        M.prepend_cover(doc, _cover(ctx, "技术文件"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    doc.save(out_path)
    return True, results
