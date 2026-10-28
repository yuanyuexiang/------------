"""解析流水线：招标文件包 zip → TRM。

支持两种输入：
- 包级 zip（包N_完整招标文件_*.zip）→ 单包 TRM
- 批次级 zip（含 分标*/包*_完整招标文件_*.zip）→ 多包 TRM
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from . import classify, docx_utils, extract, normalize, scoring, unpack
from .trm import TRM, PackageTRM

PKG_ZIP_PAT = re.compile(r"(?P<package>包\d+|[A-Z]+\d+-\d+)_完整(?:招标|采购)文件_\d+")
SUB_DIR_PAT = re.compile(r"分标(\d+)([^/]*)")
ECP_IDENTITY_PAT = re.compile(r"(\d{6}-\d{7}-\d{4})、([^/]+?)、(包\d+)(?:/|$)")


def parse_package_dir(root: str, files: list[str], trm: TRM,
                      sub_no: str = "", sub_name: str = "", pkg_no: str = "") -> None:
    """解析一个"包"目录（已解压），结果写入 trm。"""
    manifest = classify.build_manifest(root, files)
    pkg = PackageTRM(sub_no=sub_no, sub_name=sub_name, pkg_no=pkg_no)

    main_rel = manifest.first(classify.MAIN_DOC)
    if main_rel:
        identities = {(m.group(1), m.group(2), m.group(3)) for m in ECP_IDENTITY_PAT.finditer(main_rel)}
        if len(identities) == 1:
            code, name, number = identities.pop()
            if not pkg_no or pkg_no == number:
                pkg.sub_no, pkg.sub_name, pkg.pkg_no = code, name, number
    if main_rel:
        doc = docx_utils.load(os.path.join(root, main_rel))
        if not trm.batch_name:
            trm.batch_name, trm.batch_no, trm.terminology = extract.extract_batch_info(doc, main_rel)
        if not trm.prenotice:
            trm.prenotice = extract.extract_prenotice(doc)
        if not trm.rejection_rules:
            trm.rejection_rules = extract.extract_rejection_rules(doc)
        if not trm.submission_table:
            trm.submission_table = extract.extract_submission_table(doc)
        if trm.prenotice and trm.key_terms.validity_days is None:
            trm.key_terms = normalize.extract_key_terms(trm.prenotice)
        if not trm.format_blocks:
            trm.format_blocks = extract.extract_format_blocks(doc, docx_utils.split_chapters(doc))
    else:
        trm.warnings.append(f"{pkg_no or root}: 未找到六章主文件")

    ann_rel = manifest.first(classify.ANNOUNCEMENT)
    if ann_rel and (not trm.batch_name or trm.key_terms.bid_deadline is None):
        try:
            ann = docx_utils.load(os.path.join(root, ann_rel))
            if not trm.batch_name:
                trm.batch_name = extract.batch_name_from_doc(ann, limit=120)
            normalize.extract_announcement_terms(docx_utils.full_text(ann), trm.key_terms)
        except Exception as exc:
            trm.warnings.append(f"{pkg_no or root}: 招标公告解析失败 {exc}")

    goods_rel = manifest.first(classify.GOODS_LIST_XLSX)
    if goods_rel:
        pkg.materials = extract.extract_goods_list(os.path.join(root, goods_rel))

    qual_rel = manifest.first(classify.QUAL_PERF_XLSX)
    if qual_rel:
        all_rows = extract.extract_qualification(os.path.join(root, qual_rel))
        # 附件为全批次资质业绩一览表：按本包分标过滤；无法定位分标时保留全部
        key = (sub_no or "") + (sub_name or "")
        mine = [q for q in all_rows if key and (key in q.sub_name or (sub_name and sub_name in q.sub_name))]
        pkg.qualification = mine if mine else all_rows

    demand_rel = manifest.first(classify.SERVICE_DEMAND_XLSX)
    if demand_rel and pkg.pkg_no:
        rec = extract.extract_service_demand(os.path.join(root, demand_rel), pkg.pkg_no,
                                             sub_no=pkg.sub_no, sub_name=pkg.sub_name)
        if rec:
            extract.apply_service_demand(pkg, rec, trm)
            pkg.identity_source = demand_rel + "；包号=" + pkg.pkg_no
        else:
            trm.warnings.append(f"{pkg_no}: 需求一览表中未找到本包行")

    for sc_rel in manifest.by_category.get(classify.SCORING, []):
        full = os.path.join(root, sc_rel)
        if sc_rel.lower().endswith((".xlsx", ".xls")):
            tpl = scoring.parse_xlsx(full, sc_rel)
        else:
            tpl = scoring.parse_docx_name_only(sc_rel)
        if tpl and not any(t.name == tpl.name for t in trm.scoring_templates):
            trm.scoring_templates.append(tpl)

    for spec_rel in manifest.by_category.get(classify.SPEC_DOC, []):
        sd = extract.extract_spec(os.path.join(root, spec_rel), spec_rel)
        if sd and (sd.spec_id or sd.param_rows or sd.n_paragraphs > 10):
            pkg.spec_docs.append(sd)
    # 同一规范书正文与封面 docx 都会命中，按 spec_id 去重，保留参数行多的；都无参数表时保留正文长的
    dedup = {}
    for sd in pkg.spec_docs:
        key = sd.spec_id or sd.source
        if key not in dedup or (len(sd.param_rows), sd.n_paragraphs) > (len(dedup[key].param_rows), dedup[key].n_paragraphs):
            dedup[key] = sd
    pkg.spec_docs = list(dedup.values())
    # 需求表项目名称与规范正文/文件名匹配时，隔离混入的其他项目封面。
    if pkg.project_name:
        matched = [sd for sd in pkg.spec_docs if pkg.project_name in sd.source
                   or pkg.project_name in sd.title]
        if matched:
            for sd in pkg.spec_docs:
                if sd not in matched:
                    trm.warnings.append(f"{pkg.pkg_no}: 排除与需求清单项目名称不一致的规范文件：{sd.source}")
            pkg.spec_docs = matched

    trm.packages.append(pkg)


def parse(zip_path: str, workdir: Optional[str] = None) -> TRM:
    workdir = workdir or tempfile.mkdtemp(prefix="jb_parse_")
    res = unpack.unpack(zip_path, workdir)
    trm = TRM(source_zip=os.path.basename(zip_path))

    # 找出所有"包"目录（嵌套 zip 解压后的同名目录）
    pkg_dirs = {}
    for f in res.files:
        m = PKG_ZIP_PAT.search(f)
        if not m:
            continue
        parts = f.replace("\\", "/").split("/")
        for i, part in enumerate(parts):
            if PKG_ZIP_PAT.search(part) and not part.endswith(".zip"):
                pkg_root = "/".join(parts[: i + 1])
                pkg_dirs.setdefault(pkg_root, []).append("/".join(parts[i + 1:]))
                break

    if pkg_dirs:
        for pkg_root, files in sorted(pkg_dirs.items()):
            sub_no = sub_name = pkg_no = ""
            msub = SUB_DIR_PAT.search(pkg_root)
            if msub:
                sub_no, sub_name = "分标" + msub.group(1), msub.group(2)
            mpkg = PKG_ZIP_PAT.search(pkg_root)
            if mpkg:
                pkg_no = mpkg.group("package")
            parse_package_dir(os.path.join(workdir, pkg_root), files, trm,
                              sub_no=sub_no, sub_name=sub_name, pkg_no=pkg_no)
    else:
        # zip 本身就是一个包；分标/包号从 zip 路径推断
        sub_no = sub_name = pkg_no = ""
        msub = SUB_DIR_PAT.search(zip_path)
        if msub:
            sub_no, sub_name = "分标" + msub.group(1), msub.group(2).split("/")[0]
        mpkg = PKG_ZIP_PAT.search(os.path.basename(zip_path))
        if mpkg:
            pkg_no = mpkg.group("package")
        parse_package_dir(workdir, res.files, trm,
                          sub_no=sub_no, sub_name=sub_name, pkg_no=pkg_no)
    return trm


@dataclass
class PackageFiles:
    """文档引擎需要回读的原始文件：六章主文件（母版）与各规范书 docx（逐条响应）。"""
    main_doc: Optional[str] = None
    spec_docs: dict[str, str] = field(default_factory=dict)   # spec_id（无 ID 用 source）→ 绝对路径


def package_files(zip_path: str, pkg: Optional[PackageTRM] = None, sub_no: str = "", pkg_no: str = "",
                  workdir: Optional[str] = None) -> PackageFiles:
    """解压招标文件包，定位指定分标/包的主文件与规范书原件。workdir 生命周期由调用方管理。

    批次级 zip 含多个包时按 分标号 > 包号 匹配，匹配不到不采用其他包原件；候选不唯一时显式报错。
    """
    if pkg is not None:
        sub_no, pkg_no = sub_no or pkg.sub_no, pkg_no or pkg.pkg_no
    workdir = workdir or tempfile.mkdtemp(prefix="jb_master_")
    res = unpack.unpack(zip_path, workdir)
    out = PackageFiles()
    cands = [f for f in res.files if classify.classify_file(f) == classify.MAIN_DOC]

    def matches(rel: str) -> bool:
        msub, mpkg = SUB_DIR_PAT.search(rel), PKG_ZIP_PAT.search(rel)
        identities = list(ECP_IDENTITY_PAT.finditer(rel))
        if identities and re.fullmatch(r"\d{6}-\d{7}-\d{4}", sub_no):
            if not any(m.group(1) == sub_no and (not pkg_no or m.group(3) == pkg_no) for m in identities):
                return False
        return (not msub or not sub_no or "分标" + msub.group(1) == sub_no) and (
            not mpkg or not pkg_no or mpkg.group("package") == pkg_no)

    # 仅在指定分标/包内选取。单包 ZIP 可能没有包目录，此时只接受唯一候选。
    cands = [f for f in cands if matches(f)]
    if len(cands) > 1:
        raise ValueError("本包主文件不唯一，需人工核对原件")
    if cands:
        out.main_doc = os.path.join(workdir, cands[0])
    for sd in (pkg.spec_docs if pkg is not None else []):
        src = sd.source.replace("\\", "/")
        hits = [f for f in res.files if matches(f) and (
            f.replace("\\", "/") == src or f.replace("\\", "/").endswith("/" + src))]
        if len(hits) != 1:
            raise ValueError(f"本包规范书原件缺失或不唯一：{src}")
        out.spec_docs[sd.spec_id or sd.source] = os.path.join(workdir, hits[0])
    return out


def main_doc_for_package(zip_path: str, sub_no: str = "", pkg_no: str = "",
                         workdir: Optional[str] = None) -> Optional[str]:
    """六章主文件绝对路径（母版用）；见 package_files。"""
    return package_files(zip_path, None, sub_no, pkg_no, workdir).main_doc
