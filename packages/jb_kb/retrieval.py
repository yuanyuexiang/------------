"""素材检索（原型：进程内 BM25-lite，中文二元组 + 拉丁词；S2 后半切 pgvector 混合检索时保持本接口）。

检索对象是"片段"（Chunk）：话术库段落、历史标书章节切片、产品特性。返回带来源 ID，供写作 Agent 引用溯源。
事实类查询（证书数量、业绩条数）不走这里，直接查档案结构化字段。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .models import CompanyProfile

_CJK = re.compile(r"[一-龥]+")
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def tokenize(text: str) -> list[str]:
    toks = [t.lower() for t in _LATIN.findall(text)]
    for run in _CJK.findall(text):
        toks.extend(run[i:i + 2] for i in range(len(run) - 1))
    return toks


@dataclass
class Chunk:
    id: str
    kind: str           # boilerplate | bid_history | product_feature
    topic: str
    text: str
    source: str = ""
    approved: bool = False


@dataclass
class Hit:
    chunk: Chunk
    score: float


@dataclass
class Index:
    chunks: list[Chunk] = field(default_factory=list)
    _df: Counter = field(default_factory=Counter)
    _tf: list[Counter] = field(default_factory=list)
    _len: list[int] = field(default_factory=list)

    def add(self, chunk: Chunk) -> None:
        toks = tokenize(chunk.text + " " + chunk.topic)
        self.chunks.append(chunk)
        self._tf.append(Counter(toks))
        self._len.append(len(toks))
        self._df.update(set(toks))

    def search(self, query: str, top_k: int = 5, kinds: tuple[str, ...] = (), approved_only: bool = False) -> list[Hit]:
        q = tokenize(query)
        if not q or not self.chunks:
            return []
        n = len(self.chunks)
        avg = sum(self._len) / n
        k1, b = 1.5, 0.75
        hits: list[Hit] = []
        for i, ch in enumerate(self.chunks):
            if kinds and ch.kind not in kinds:
                continue
            if approved_only and not ch.approved:
                continue
            tf = self._tf[i]
            score = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                f = tf[t]
                score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * self._len[i] / avg))
            if score > 0:
                hits.append(Hit(ch, score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]


def build_index(profile: CompanyProfile) -> Index:
    idx = Index()
    for i, bp in enumerate(profile.boilerplates):
        idx.add(Chunk(id=f"bp-{i}", kind="boilerplate", topic=bp.topic, text=bp.text, source=bp.source, approved=bp.approved))
    for p in profile.products:
        for j, f in enumerate(p.features):
            idx.add(Chunk(id=f"pf-{p.model}-{j}", kind="product_feature", topic=p.name, text=f, source=p.source, approved=True))
    return idx
