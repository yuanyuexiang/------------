from jb_parser.pipeline import apply_goods_identity
from jb_parser.trm import Material, PackageTRM


def test_goods_identity_uses_document_filename_and_unique_package_code():
    pkg = PackageTRM(pkg_no='包1', materials=[Material(pkg='包1', sub_no='182635-1208008-109')])
    apply_goods_identity(pkg, '货物清单_182635_通信监控系统20260904_202606_845.xlsx', '182635')
    assert (pkg.sub_no, pkg.sub_name) == ('182635-1208008-109', '通信监控系统')
    assert '清单文件名' in pkg.identity_source


def test_goods_identity_does_not_guess_or_overwrite_conflicts():
    source = '货物清单_182635_通信监控系统20260904_202606_845.xlsx'
    for pkg in [PackageTRM(pkg_no='包2'),
                PackageTRM(pkg_no='包1', sub_name='已核实名称', materials=[Material(pkg='包1', sub_no='182635-1')]),
                PackageTRM(pkg_no='包1', materials=[Material(pkg='包1', sub_no='182635-1'), Material(pkg='包1', sub_no='182635-2')])]:
        before = pkg.model_dump()
        apply_goods_identity(pkg, source, '182635')
        assert pkg.model_dump() == before
    pkg = PackageTRM(pkg_no='包1', materials=[Material(pkg='包1', sub_no='182635-1')])
    apply_goods_identity(pkg, source, 'OTHER')
    assert not pkg.sub_name
    apply_goods_identity(pkg, '通信监控系统.xlsx', '182635')
    assert not pkg.sub_name
