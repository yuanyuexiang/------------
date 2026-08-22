"""jb-kb：企业知识库（P2 起落多表：主档 + 证照/人员/业绩/财务/产品/检测报告/话术 + 附件）。"""
from .expiry import expiry_report  # noqa: F401
from .models import CompanyProfile  # noqa: F401
from .profile_builder import build_profile  # noqa: F401
