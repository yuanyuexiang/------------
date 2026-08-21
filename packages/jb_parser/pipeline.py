"""解析流水线：招标文件包 zip → TRM。

支持两种输入：
- 包级 zip（包N_完整招标文件_*.zip）→ 单包 TRM
- 批次级 zip（含 分标*/包*_完整招标文件_*.zip）→ 多包 TRM
"""
from __future__ import annotations

import os
import re
import tempfile
from typing import List, Optional

from . import classify, docx_utils, extract, normalize, scoring, unpack
from .trm import TRM, PackageTRM

PKG_ZIP_PAT = re.compile(r"包(\d+)_完整(?:招标|采购)文件_\d+")
SUB_DIR_PAT = re.compile(r"分标(\d+)([^/]*)")


def parse_package_dir(root: str, files: List[str], trm: TRM,
                      sub_no: str = "", sub_name: str = "", pkg_no: str = "") -> None:
    """解析一个"包"目录（已解压），结果写入 trm。"""
    manifest = classify.build_manifest(root, files)
    pkg = PackageTRM(sub_no=sub_no, sub_name=sub_name, pkg_no=pkg_no)

    main_rel = manifest.first(classify.MAIN_DOC)
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
    else:
        trm.warnings.append("{}: 未找到六章主文件".format(pkg_no or root))

    if not trm.batch_name:
        ann_rel = manifest.first(classify.ANNOUNCEMENT)
        if ann_rel:
            try:
                ann = docx_utils.load(os.path.join(root, ann_rel))
                trm.batch_name = extract.batch_name_from_doc(ann, limit=120)
            except Exception:
                pass

    goods_rel = manifest.first(classify.GOODS_LIST_XLSX)
    if goods_rel:
        pkg.materials = extract.extract_goods_list(os.path.join(root, goods_rel))

    qual_rel = manifest.first(classify.QUAL_PERF_XLSX)
    if qual_rel:
        pkg.qualification = extract.extract_qualification(os.path.join(root, qual_rel))

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
        if sd and (sd.spec_id or sd.param_rows):
            pkg.spec_docs.append(sd)
    # 同一规范书正文与封面 docx 都会命中，按 spec_id 去重，保留参数行多的
    dedup = {}
    for sd in pkg.spec_docs:
        key = sd.spec_id or sd.source
        if key not in dedup or len(sd.param_rows) > len(dedup[key].param_rows):
            dedup[key] = sd
    pkg.spec_docs = list(dedup.values())

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
                pkg_no = "包" + mpkg.group(1)
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
            pkg_no = "包" + mpkg.group(1)
        parse_package_dir(workdir, res.files, trm,
                          sub_no=sub_no, sub_name=sub_name, pkg_no=pkg_no)
    return trm
