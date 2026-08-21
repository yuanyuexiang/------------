"""价格模块：报价底稿校验（五重）+ 评标基准价区间模拟。

报价决策由人做；本模块只做：
1. 校验（典型案例库 6/7/8/12 + 前附表 3.2.5）：单位量级、增值税税率、小数位、报价超限、不平衡报价、零单价、限价
2. 模拟：区间平均价浮动法（前附表之六原文公式）在浮动系数 C 未知（开标现场抽取）时的得分区间
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field


class PriceLine(BaseModel):
    row: int
    desc: str = ""
    qty: float = 1
    unit_price_ex_tax: Optional[float] = None   # 未含税单价（元）
    vat_rate: Optional[float] = None            # 13 / 9 / 6 / 3（%）
    spec_id: str = ""                            # 不平衡报价按固化规范 ID 分组


class PriceSheet(BaseModel):
    pkg_no: str = ""
    lines: list[PriceLine] = Field(default_factory=list)
    max_price_yuan: Optional[float] = None       # 最高限价
    currency_unit: str = "元"                    # 元 | 万元（须与表头一致）

    def total_ex_tax(self) -> float:
        return sum((ln.unit_price_ex_tax or 0) * ln.qty for ln in self.lines)

    def total_with_tax(self) -> float:
        return sum((ln.unit_price_ex_tax or 0) * ln.qty * (1 + (ln.vat_rate or 0) / 100) for ln in self.lines)


class Issue(BaseModel):
    level: str          # 否决 | 扣分 | 建议
    rule: str
    message: str
    rows: list[int] = Field(default_factory=list)


VALID_VAT = (13.0, 9.0, 6.0, 5.0, 3.0, 1.0, 0.0)


def validate(sheet: PriceSheet, goods_vat: float = 13.0, unbalanced_pct: float = 12.0,
             peer_avg: Optional[float] = None, over_limit_pct: Optional[float] = None) -> list[Issue]:
    issues: list[Issue] = []
    # 1. 零单价 / 缺报价（前附表 3.2.5：未含税单价不得为零，不接受赠予）
    zero = [ln.row for ln in sheet.lines if ln.unit_price_ex_tax is None or ln.unit_price_ex_tax <= 0]
    if zero:
        issues.append(Issue(level="否决", rule="零单价", message="未含税单价为零或缺失（不接受赠予）", rows=zero))
    # 2. 税率（案例 6(2)：不按法规填报增值税税率）
    bad_vat = [ln.row for ln in sheet.lines if ln.vat_rate is None or ln.vat_rate not in VALID_VAT]
    if bad_vat:
        issues.append(Issue(level="否决", rule="税率错误", message="增值税税率缺失或非法定税率", rows=bad_vat))
    odd_vat = [ln.row for ln in sheet.lines if ln.vat_rate is not None and ln.vat_rate in VALID_VAT and ln.vat_rate != goods_vat]
    if odd_vat:
        issues.append(Issue(level="建议", rule="税率核对", message=f"税率与货物常规税率 {goods_vat:g}% 不同（小规模纳税人可填征收率），请确认", rows=odd_vat))
    # 3. 小数位（ECP 识别至小数点后 6 位；单价小数点错位会导致量级错误）
    many_dec = [ln.row for ln in sheet.lines if ln.unit_price_ex_tax is not None and len(f"{ln.unit_price_ex_tax:.10f}".rstrip("0").split(".")[1]) > 6]
    if many_dec:
        issues.append(Issue(level="否决", rule="小数位", message="单价小数位超过 6 位", rows=many_dec))
    # 4. 货币单位量级（案例 6(1)：万元当元 → 百倍至万倍异常）
    if peer_avg and sheet.lines:
        total = sheet.total_ex_tax()
        if total > peer_avg * 50 or total < peer_avg / 50:
            issues.append(Issue(level="否决", rule="货币单位", message=f"总价 {total:,.2f} 与参考均价 {peer_avg:,.2f} 相差百倍以上，疑似元/万元混淆"))
    # 5. 报价超限（案例 7：超过其余投标人均价既定百分比）
    if peer_avg and over_limit_pct is not None and sheet.total_ex_tax() > peer_avg * (1 + over_limit_pct / 100):
        issues.append(Issue(level="否决", rule="报价超限", message=f"总价超过参考均价 {over_limit_pct:g}% 上限"))
    # 6. 最高限价（前附表 3.2.4）
    if sheet.max_price_yuan is not None and sheet.total_with_tax() > sheet.max_price_yuan:
        issues.append(Issue(level="否决", rule="超最高限价", message=f"含税总价 {sheet.total_with_tax():,.2f} > 最高限价 {sheet.max_price_yuan:,.2f}"))
    # 7. 不平衡报价（案例 8：同固化规范 ID 且描述相同的行，单价偏离均值 ±12%）
    groups: dict[tuple[str, str], list[PriceLine]] = {}
    for ln in sheet.lines:
        if ln.spec_id.startswith("9999") and ln.unit_price_ex_tax:
            groups.setdefault((ln.spec_id, ln.desc), []).append(ln)
    for (sid, _desc), lns in groups.items():
        if len(lns) < 2:
            continue
        avg = sum(x.unit_price_ex_tax for x in lns) / len(lns)
        off = [x.row for x in lns if abs(x.unit_price_ex_tax - avg) / avg * 100 > unbalanced_pct]
        if off:
            issues.append(Issue(level="否决", rule="不平衡报价", message=f"规范 {sid} 同物资单价偏离均值超 ±{unbalanced_pct:g}%", rows=off))
    return issues


# ---------- 区间平均价浮动法（前附表之六原文） ----------

@dataclass
class Simulation:
    my_price: float
    benchmark_range: tuple[float, float]
    score_range: tuple[float, float]
    detail: list[dict] = field(default_factory=list)


def _effective(prices: list[float], w1: float, w2: float) -> list[float]:
    """按初评合格人数分档剔除极值后，取落在 A1*[1+W1,1+W2] 区间内的有效报价；区间为空则全部有效。"""
    ps = sorted(prices)
    n = len(ps)
    if n <= 5:
        pool = ps
    elif n <= 10:
        pool = ps[1:-1]
    elif n <= 20:
        pool = ps[1:-2]
    elif n <= 30:
        pool = ps[2:-3]
    else:
        pool = ps[3:-4]
    a1 = sum(pool) / len(pool)
    inside = [p for p in pool if a1 * (1 + w1) < p < a1 * (1 + w2)]
    return inside or pool


def simulate_interval_avg(my_price: float, peer_prices: list[float], c_candidates: list[float],
                          w1: float = -0.2, w2: float = 0.1, n_high: float = 1.0, n_low: float = 0.5,
                          weight: float = 30.0) -> Simulation:
    """价格分 = 100 − 100×n×|报价−基准价|/基准价；报价≥基准价用 n_high，<基准价用 n_low；基准价=A2×(1−C)。
    C 在开标现场随机抽取 → 对候选 C 逐一计算，给出得分区间。"""
    prices = peer_prices + [my_price]
    eff = _effective(prices, w1, w2)
    a2 = sum(eff) / len(eff)
    detail, benches, scores = [], [], []
    for c in c_candidates:
        bench = a2 * (1 - c)
        n = n_high if my_price >= bench else n_low
        raw = max(0.0, 100 - 100 * n * abs(my_price - bench) / bench)
        score = raw * weight / 100
        detail.append({"C": c, "benchmark": round(bench, 2), "raw": round(raw, 2), "score": round(score, 2)})
        benches.append(bench)
        scores.append(score)
    return Simulation(my_price, (min(benches), max(benches)), (min(scores), max(scores)), detail)
