"""母版切片装配：用合成的"招标文件六章"docx 验证切片、跨 run 填空、表格行填充、媒体清理与回退（不依赖样本）。"""
import io
import os
import struct
import zipfile

import docx
import pytest
from docx.shared import Pt
from jb_docgen import generate
from jb_docgen import master as M
from jb_kb.models import Certificate, CompanyProfile, FinancialYear, Performance, Person, Product
from jb_parser.trm import TRM, PackageTRM, SpecDoc, SpecParamRow


def _png() -> bytes:
    """1x1 PNG（母版价格段里的图片，切片后应被清掉）。"""
    import zlib
    raw = b"\x00\xff\x00\x00"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _table(d, rows):
    t = d.add_table(rows=len(rows), cols=len(rows[0]))
    for r, vals in enumerate(rows):
        for c, v in enumerate(vals):
            t.rows[r].cells[c].text = v
    return t


def _master(path: str) -> str:
    d = docx.Document()
    d.add_paragraph("第一章  招标公告")
    d.add_paragraph("公告正文")
    d.add_paragraph("第六章  投标文件格式")
    d.add_paragraph("价格文件")
    d.add_paragraph("投标函")
    d.add_paragraph("致：招标人")
    d.add_paragraph().add_run().add_picture(io.BytesIO(_png()))
    d.add_paragraph("商务文件")
    d.add_paragraph("（一）商务偏差表（可在投标工具直接选择无/有偏差，上传投标工具路径：商务文件-按钮“编辑”）")
    d.add_paragraph("1.商务偏差表（格式）")
    _table(d, [["序号", "招标文件条目号", "招标文件条款", "投标文件条款", "偏差说明"], ["", "", "", "", ""], ["", "", "", "", ""],
               ["投标人声明：针对本招标标的，除本表所列偏差外完全响应。", "", "", "", ""]])
    d.add_paragraph("投标人基本情况表1")
    _table(d, [["投标人名称", "", "", ""], ["注册地址", "", "邮政编码", ""],
               ["法定代表人（单位负责人）", "姓名", "", "技术职称"],
               ["统一社会信用代码", "", "高级职称人员", ""], ["成立时间", "", "员工总人数：", ""]])
    d.add_paragraph("7.财务状况")
    # 真实表头"年份/财务指标"横跨两列（序号列 + 指标列），年份列与数据列靠网格列对齐
    _table(d, [["年份\n财务指标", "年份\n财务指标", "XX年", "XX年", "XX年", "平均"], ["1", "注册资本金", "", "", "", ""],
               ["2", "资产总额", "", "", "", ""], ["2", "资产负债率＝负债总额÷资产总额×100%", "", "", "", ""],
               ["4", "营业收入净额", "", "", "", ""], ["5", "净利润", "", "", "", ""]])
    d.add_paragraph("企业营业执照（或事业单位法人证书或其他组织登记证书）副本")
    d.add_paragraph("6.1符合招标公告投标人资格要求的证明文件")
    d.add_paragraph("法定代表人（单位负责人）授权委托书")
    p = d.add_paragraph()
    r1 = p.add_run("_____________（投标人名称）为中华人民共和国合法企业，法定地址：")
    r1.font.size = Pt(14)
    p.add_run("。")
    p = d.add_paragraph()
    p.add_run("________________（营业执照法定代表人（单位负责人））特授权")
    p.add_run("__________")
    p.add_run("代表我方全权办理XX（招标编号）（分标编号及名称）（包号）（包名称）项目的投标。")
    d.add_paragraph("投标人名称：")
    d.add_paragraph("地址：")
    d.add_paragraph("投标人：（盖章）")
    d.add_paragraph("职务：____________")
    d.add_paragraph("三、技术文件")
    d.add_paragraph("1.技术偏差表")
    d.add_paragraph("项目名称：项目编号：分标名称：分标编号：包名称：包号：")
    _table(d, [["序号", "偏差事项", "招标文件要求", "投标文件响应", "偏差说明"], ["", "", "", "", ""], ["", "", "", "", ""],
               ["", "其他", "", "", ""], ["投标人声明：除本表所列偏差外完全响应。", "", "", "", ""]])
    d.add_paragraph("供货及运行业绩表")
    _table(d, [["序号", "产品型式", "工程名称", "数量（单位）或金额（万元）", "投运时间", "联系人及电话", "备注"],
               ["", "", "", "", "", "", ""], ["编制说明：按投运时间倒序。", "", "", "", "", "", ""]])
    d.add_paragraph("2.技术特性参数表（格式）")
    _table(d, [["技术特性参数表（格式）", "", "", "", ""], ["项目单位：", "项目名称：", "", "", ""],
               ["序号", "名称", "单位", "招标人要求值", "投标人保证值"], ["1", "", "", "", ""], ["2", "", "", "", ""],
               ["…", "", "", "", ""], ["编制说明：保证值须填具体数值。", "", "", "", ""]])
    d.add_paragraph("8.售后服务保障及承诺")
    d.add_paragraph("14.认证证书（格式）")
    _table(d, [["信息事项", "认证机构", "证书编号", "认证事项范围", "有效期限"], ["", "", "", "", ""], ["…….", "", "", "", ""]])
    d.add_paragraph("主要技术人员（格式）")
    _table(d, [["序号", "岗位", "现担任职务/专业", "工作经历", "通讯电话和地址", "备注"],
               ["1", "技术总负责人", "", "", "", ""], ["2", "生产进度负责人", "", "", "", ""], ["", "", "", "", "", ""]])
    d.save(path)
    return path


def _spec(spec_id="9999-500000001-00001"):
    return SpecDoc(spec_id=spec_id, structured=True, param_rows=[
        SpecParamRow(row=1, name="授权", required="★配置网络设备授权不小于256个", star=True),
        SpecParamRow(row=2, name="衰减", required="≤0.21"),
    ])


def _profile():
    return CompanyProfile(
        name="测试企业", credit_code="9100X", address="南京市", legal_person="张三", founded="2010-01-01",
        authorized_rep="李四", authorized_rep_title="经理", senior_engineers=3, staff_total=80,
        certificates=[Certificate(name="质量管理体系认证证书", cert_type="体系认证", number="Q-001", issuer="认证中心",
                                  valid_until="2027-01-01"),
                      Certificate(name="营业执照", cert_type="证照")],
        personnel=[Person(name="王五", title="高级工程师", major="通信", credentials=["身份证", "职称证书"])],
        performances=[Performance(project="项目A", buyer="国网某公司", amount_wan=120, signed_date="2025-01-01",
                                  commissioned_date="2025-06-01", evidence=["合同", "发票"])],
        financials=[FinancialYear(year="2024", revenue_wan=5000, net_profit_wan=300, asset_wan=8000, liability_ratio="40%"),
                    FinancialYear(year="2023", revenue_wan=4000, net_profit_wan=200, asset_wan=7000, liability_ratio="42%")],
        products=[Product(model="T-1", name="综合网管", category="综合网管",
                          params={"网络设备授权": "512个", "衰减系数": "13.2"})])


def _trm_pkg():
    trm = TRM(batch_name="测试批次", batch_no="T-2026-01")
    pkg = PackageTRM(sub_no="分标1", sub_name="综合网管", pkg_no="包1", project_name="测试项目",
                     spec_docs=[_spec(), _spec("9999-500000001-00002")])
    return trm, pkg


def _text(path):
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for r in t.rows:
            parts.append(" | ".join(c.text for c in r.cells))
    return "\n".join(parts), d


def test_split_parts_and_carve(tmp_path):
    path = _master(str(tmp_path / "m.docx"))
    parts = M.split_parts(docx.Document(path))
    assert set(parts) == {"price", "commercial", "technical"}
    com = M.carve(path, "commercial")
    texts = [p.text for p in com.paragraphs]
    assert texts[0] == "商务文件" and "投标函" not in texts and "三、技术文件" not in texts
    assert "第一章  招标公告" not in texts
    assert not com.inline_shapes and all(r.reltype.split("/")[-1] != "image" for r in com.part.rels.values())


def test_generate_from_master(tmp_path):
    master = _master(str(tmp_path / "m.docx"))
    trm, pkg = _trm_pkg()
    res = generate(trm, pkg, _profile(), str(tmp_path / "out"), master_docx=master)
    assert res.mode == {"commercial": "master", "technical": "master"}, res.notes

    text, d = _text(res.commercial_path)
    # 切片 + 指引行删除 + 封面
    assert "投标函" not in text.split("商务文件")[1][:50] and "上传投标工具路径" not in text
    assert d.paragraphs[0].text == "投标文件"
    # 跨 run 填空且保留首 run 字号
    p = next(p for p in d.paragraphs if "（投标人名称）为中华人民共和国" in p.text)
    assert p.text == "测试企业（投标人名称）为中华人民共和国合法企业，法定地址：南京市。"
    assert len(p.runs) == 1 and p.runs[0].font.size == Pt(14)
    assert "特授权李四" in text and "T-2026-01（招标编号）" in text and "职务：经理" in text
    # 标签行：空的补值，已有内容不动
    assert "投标人名称：测试企业" in text and "地址：南京市" in text and "投标人：（盖章）" in text
    # 基本情况表 / 财务表 / 偏差表
    assert "投标人名称 | 测试企业" in text and "统一社会信用代码 | 9100X | 高级职称人员 | 3" in text
    assert "姓名 | 张三" in text and "员工总人数：80" in text
    assert "2024年 | 2023年 | XX年 | 平均" in text and "资产总额 | 8000万元 | 7000万元 |" in text
    assert "资产负债率＝负债总额÷资产总额×100% | 40% | 42%" in text and "净利润 | 300万元" in text
    assert "1 | / | / | / | 无偏差" in text and "投标人声明" in text
    # 扫描件待补充 + 证书清单
    assert "【待补充：营业执照扫描件插入】" in text and "质量管理体系认证证书（有效期至 2027-01-01）" in text

    text, d = _text(res.technical_path)
    assert "商务偏差表" not in text and d.paragraphs[0].text == "投标文件"
    assert "项目名称：测试项目项目编号：T-2026-01分标名称：综合网管分标编号：分标1包名称：包1包号：包1" in text
    # 技术偏差表：衰减偏差进表，"其他"行与声明行保留
    assert "1 | 参数表第2行 衰减 | ≤0.21 | 13.2" in text and " | 其他 | " in text and "投标人声明" in text
    # 参数表：两本规范书 → 模板表克隆，保证值为具体值；模板序号/省略号行被数据替换
    params = [t for t in d.tables if len(t.rows) > 2 and "投标人保证值" in " ".join(c.text for c in t.rows[2].cells)]
    assert len(params) == 2 and "技术规范书 9999-500000001-00002" in text
    assert "1 | 授权 |  | ★配置网络设备授权不小于256个 | 512个" in text and "… | " not in text
    # 业绩 / 人员 / 认证按表头映射
    assert "1 | T-1 | 项目A | 120万元 | 2025-06-01" in text and "项目A 的合同扫描件" in text
    assert "1 | 技术总负责人 | 王五（高级工程师） |" in text
    assert "质量管理体系认证证书 | 认证中心 | Q-001 |  | 2027-01-01" in text
    assert "售后服务保障及承诺（话术库暂无审核通过的段落）" in text
    assert res.export_blocked
    with zipfile.ZipFile(res.technical_path) as z:
        assert not [n for n in z.namelist() if n.startswith("word/media/")]


def test_fallback_when_master_has_no_parts(tmp_path):
    plain = docx.Document()
    plain.add_paragraph("没有格式章的文档")
    plain.save(str(tmp_path / "plain.docx"))
    trm, pkg = _trm_pkg()
    res = generate(trm, pkg, _profile(), str(tmp_path / "out"), master_docx=str(tmp_path / "plain.docx"))
    assert res.mode == {"commercial": "plain", "technical": "plain"}
    assert len(res.notes) == 2 and os.path.exists(res.commercial_path) and os.path.exists(res.technical_path)


def test_attachment_pictures(tmp_path):
    img = tmp_path / "lic.png"
    img.write_bytes(_png())
    master = _master(str(tmp_path / "m.docx"))
    prof = _profile()
    prof.certificates[1].attachments = ["a1"]
    prof.certificates[0].attachments = ["a2"]
    trm, pkg = _trm_pkg()
    res = generate(trm, pkg, prof, str(tmp_path / "out"), master_docx=master,
                   attachment_paths={"a1": str(img), "a2": str(tmp_path / "scan.pdf")})
    text, d = _text(res.commercial_path)
    assert "【待补充：营业执照扫描件插入】" not in text and len(d.inline_shapes) == 1
    assert "scan.pdf 非图片格式" in text


@pytest.mark.parametrize("line", ["价格文件", "1.价格文件", "一、价格文件", "三、技术文件", "3.技术文件", "2.商务文件"])
def test_part_separator_variants(line):
    assert M.PART_PAT.match(M.norm(line))
