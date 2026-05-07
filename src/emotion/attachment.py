"""L3 RelationshipContext: 依恋理论动态化。

不是给用户贴标签，而是动态感知当前的依恋系统激活程度。
输出: attachment_activation + distance_suggestion。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .recognition import RecognitionResult
from .cognitive import CognitiveResult


class DistanceSuggestion(str, Enum):
    """回复距离感建议。"""
    CLOSE = "close"       # 贴近（高共情、高回应）
    NEUTRAL = "neutral"   # 中性（正常互动）
    DISTANT = "distant"   # 留白（给空间、不追问）


@dataclass
class AttachmentResult:
    activation: float = 0.0                      # 依恋系统激活程度 0~1
    distance: DistanceSuggestion = DistanceSuggestion.NEUTRAL
    dependency_signal: float = 0.0               # 依赖信号强度 0~1
    avoidance_signal: float = 0.0                # 回避信号强度 0~1


_DEPENDENCY_WORDS = {
    "没有你不行", "你别走", "求你", "不能没有你",
    "我只有你", "别离开我", "你是我的全部",
    "你在吗", "你怎么不回我", "你是不是不在乎",
}

_AVOIDANCE_WORDS = {
    "算了", "无所谓", "随便", "别管我", "没事",
    "不用了", "我自己可以", "别烦我",
}

_SECURE_WORDS = {
    "谢谢你", "我知道", "没关系", "理解", "好的",
    "我想聊聊", "你觉得呢",
}


class AttachmentAnalyzer:
    """L3: 依恋理论动态上下文分析。"""

    def __init__(self):
        self._recent_dependency: list[float] = []
        self._recent_avoidance: list[float] = []

    def analyze(self, text: str, l1: RecognitionResult,
                l2: CognitiveResult, context: dict | None = None) -> AttachmentResult:
        ctx = context or {}

        dep_hits = sum(1 for w in _DEPENDENCY_WORDS if w in text)
        dependency = min(dep_hits / 2.0, 1.0)

        avoid_hits = sum(1 for w in _AVOIDANCE_WORDS if w in text)
        avoidance = min(avoid_hits / 2.0, 1.0)

        secure_hits = sum(1 for w in _SECURE_WORDS if w in text)

        # 维护滑动窗口
        self._recent_dependency.append(dependency)
        self._recent_avoidance.append(avoidance)
        if len(self._recent_dependency) > 10:
            self._recent_dependency.pop(0)
            self._recent_avoidance.pop(0)

        avg_dep = sum(self._recent_dependency) / len(self._recent_dependency)
        avg_avoid = sum(self._recent_avoidance) / len(self._recent_avoidance)

        # 激活度 = 情绪强度 + 依赖信号 + 认知扭曲
        activation = min(
            0.40 * l1.intensity
            + 0.30 * avg_dep
            + 0.20 * (l2.distortion_score if l2.activated else 0.0)
            + 0.10 * avg_avoid,
            1.0,
        )

        distance = self._suggest_distance(activation, avg_dep, avg_avoid, secure_hits)

        return AttachmentResult(
            activation=activation,
            distance=distance,
            dependency_signal=avg_dep,
            avoidance_signal=avg_avoid,
        )

    def _suggest_distance(self, activation: float, dep: float,
                          avoid: float, secure: int) -> DistanceSuggestion:
        if avoid > 0.4 and dep < 0.2:
            return DistanceSuggestion.DISTANT
        if dep > 0.5 or activation > 0.7:
            return DistanceSuggestion.CLOSE
        if secure >= 2:
            return DistanceSuggestion.NEUTRAL
        return DistanceSuggestion.NEUTRAL
