"""EmotionEngine: E3-Score 情感策略路由。

心理学理论基础:
- 依恋理论 (Attachment Theory) -> 回复距离感
- 情绪调节过程模型 (Gross) -> 阶段性策略
- 非暴力沟通 NVC -> 输出结构约束
- 动机式访谈 MI (OARS) -> 改变引导策略
- 认知行为 CBT -> 认知重评触发

E3 维度:
  E (Empathy)   : 共情需求强度  ← NVC + 情绪强度
  S (Stability)  : 对话稳定度    ← 冲突概率 + 认知扭曲
  B (Boundary)   : 边界风险度    ← 风险词 + 依赖倾向
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.config import E3_BOUNDARY_THRESHOLD, E3_EMPATHY_HIGH, E3_STABILITY_LOW


# ── 词典（MVP 版，后续可替换为分类器） ──

_DISTRESS_WORDS = {
    "难过", "伤心", "哭", "崩溃", "受不了", "好累", "绝望", "心痛",
    "失眠", "焦虑", "害怕", "孤独", "想你", "后悔", "对不起",
    "不想活", "没意思", "算了",
}

_RISK_WORDS = {
    "不想活", "自杀", "割", "死", "去死", "跳楼", "安眠药",
    "跟踪", "骚扰", "报复", "威胁",
}

_CONFLICT_WORDS = {
    "你凭什么", "滚", "分手", "恶心", "讨厌你", "都怪你",
    "你从来不", "你总是", "你根本不在乎",
}

_DEPENDENCY_WORDS = {
    "没有你不行", "你别走", "求你", "不能没有你",
    "我只有你", "别离开我", "你是我的全部",
}

_COGNITIVE_DISTORTION_PATTERNS = [
    r"永远不会",
    r"所有人都",
    r"从来没有",
    r"一定是我的错",
    r"没有人.*在乎",
    r"不可能.*好",
]


class ResponsePolicy(str, Enum):
    """回复策略枚举。"""
    COMFORT = "comfort"          # 高共情安抚
    STABILIZE = "stabilize"      # 降冲突稳定
    SAFE_GUARD = "safe_guard"    # 安全降级
    DEFAULT = "default"          # 正常人格表达
    GUIDE_CHANGE = "guide_change"  # MI 引导改变


@dataclass
class E3Score:
    """三维情感评分。"""
    empathy: float = 0.0      # 0~1
    stability: float = 1.0    # 0~1 (1=非常稳定)
    boundary: float = 0.0     # 0~1 (1=极高风险)
    policy: ResponsePolicy = ResponsePolicy.DEFAULT

    def to_dict(self) -> dict:
        return {
            "empathy": round(self.empathy, 3),
            "stability": round(self.stability, 3),
            "boundary": round(self.boundary, 3),
            "policy": self.policy.value,
        }


class EmotionEngine:
    """情感引擎：分析用户输入，输出 E3Score + ResponsePolicy。"""

    def __init__(self):
        self._distortion_patterns = [re.compile(p) for p in _COGNITIVE_DISTORTION_PATTERNS]

    def _count_hits(self, text: str, word_set: set[str]) -> int:
        return sum(1 for w in word_set if w in text)

    def _detect_distortions(self, text: str) -> int:
        return sum(1 for p in self._distortion_patterns if p.search(text))

    def analyze(self, user_text: str, context: dict | None = None) -> E3Score:
        """分析单轮用户输入，返回 E3Score。

        Args:
            user_text: 用户当前消息
            context: 可选上下文 {"recent_conflict_count": int, "hour": int, ...}
        """
        ctx = context or {}
        text = user_text.strip()
        text_len = max(len(text), 1)

        # ── Empathy 维度 ──
        distress_hits = self._count_hits(text, _DISTRESS_WORDS)
        emotion_intensity = min(distress_hits / 3.0, 1.0)

        risk_for_empathy = min(self._count_hits(text, _RISK_WORDS) / 2.0, 1.0)

        # 深夜权重 (23:00 - 05:00)
        hour = ctx.get("hour", 12)
        night_boost = 0.15 if (hour >= 23 or hour < 5) else 0.0

        empathy = min(
            0.45 * emotion_intensity
            + 0.30 * risk_for_empathy
            + 0.15 * night_boost
            + 0.10 * min(ctx.get("recent_conflict_count", 0) / 3.0, 1.0),
            1.0,
        )

        # ── Stability 维度 ──
        conflict_hits = self._count_hits(text, _CONFLICT_WORDS)
        conflict_prob = min(conflict_hits / 3.0, 1.0)
        distortion_count = self._detect_distortions(text)
        contradiction_rate = min(distortion_count / 3.0, 1.0)
        drift_rate = min(ctx.get("topic_drift_count", 0) / 5.0, 1.0)

        stability = max(
            1.0 - (0.40 * conflict_prob + 0.35 * contradiction_rate + 0.25 * drift_rate),
            0.0,
        )

        # ── Boundary 维度 ──
        risk_hits = self._count_hits(text, _RISK_WORDS)
        risk_keyword_score = min(risk_hits / 2.0, 1.0)
        dependency_hits = self._count_hits(text, _DEPENDENCY_WORDS)
        dependency_risk = min(dependency_hits / 2.0, 1.0)
        coercion = 0.3 if any(w in text for w in ["你必须", "你应该", "你给我"]) else 0.0

        boundary = min(
            0.50 * risk_keyword_score
            + 0.30 * coercion
            + 0.20 * dependency_risk,
            1.0,
        )

        # ── 策略路由 ──
        policy = self._route_policy(empathy, stability, boundary, ctx)

        return E3Score(
            empathy=empathy,
            stability=stability,
            boundary=boundary,
            policy=policy,
        )

    def _route_policy(self, empathy: float, stability: float,
                      boundary: float, ctx: dict) -> ResponsePolicy:
        """策略路由决策树。"""
        # P1: 安全边界最高优先
        if boundary >= E3_BOUNDARY_THRESHOLD:
            return ResponsePolicy.SAFE_GUARD

        # P2: 高共情 + 足够稳定 -> 安抚
        if empathy >= E3_EMPATHY_HIGH and stability >= E3_STABILITY_LOW:
            return ResponsePolicy.COMFORT

        # P3: 稳定性过低 -> 先降冲突
        if stability < E3_STABILITY_LOW:
            return ResponsePolicy.STABILIZE

        # P4: 用户有改变意愿 -> MI 引导
        change_signals = {"想改变", "怎么办", "该怎么做", "帮帮我", "我想变好"}
        if any(s in ctx.get("user_text", "") for s in change_signals):
            return ResponsePolicy.GUIDE_CHANGE

        return ResponsePolicy.DEFAULT
