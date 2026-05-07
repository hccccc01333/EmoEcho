"""L1 EmotionRecognition: Gross 情绪调节过程模型。

检测用户当前情绪阶段 + 多维情绪向量。
Gross 过程模型: 情绪调节策略要根据阶段选择（触发前/爆发中/恢复期）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EmotionStage(str, Enum):
    """Gross 模型: 情绪阶段。"""
    PRE_TRIGGER = "pre_trigger"   # 触发前（平静/轻微波动）
    ERUPTION = "eruption"         # 爆发中（强烈情绪）
    RECOVERY = "recovery"         # 恢复期（情绪消退）


@dataclass
class EmotionVector:
    """多维情绪向量。"""
    sadness: float = 0.0
    anger: float = 0.0
    anxiety: float = 0.0
    loneliness: float = 0.0
    warmth: float = 0.0

    def dominant(self) -> str:
        scores = {
            "sadness": self.sadness, "anger": self.anger,
            "anxiety": self.anxiety, "loneliness": self.loneliness,
            "warmth": self.warmth,
        }
        return max(scores, key=scores.get)

    def intensity(self) -> float:
        return max(self.sadness, self.anger, self.anxiety, self.loneliness)

    def to_dict(self) -> dict:
        return {
            "sadness": round(self.sadness, 3),
            "anger": round(self.anger, 3),
            "anxiety": round(self.anxiety, 3),
            "loneliness": round(self.loneliness, 3),
            "warmth": round(self.warmth, 3),
        }


@dataclass
class RecognitionResult:
    stage: EmotionStage = EmotionStage.PRE_TRIGGER
    vector: EmotionVector = field(default_factory=EmotionVector)
    intensity: float = 0.0


_SADNESS_WORDS = {"难过", "伤心", "哭", "心痛", "后悔", "对不起", "失去", "怀念", "想你", "遗憾"}
_ANGER_WORDS = {"生气", "愤怒", "凭什么", "滚", "恶心", "讨厌", "都怪你", "不公平"}
_ANXIETY_WORDS = {"焦虑", "害怕", "担心", "紧张", "失眠", "不安", "慌", "怕"}
_LONELINESS_WORDS = {"孤独", "一个人", "没人理", "没有人", "寂寞", "冷清"}
_WARMTH_WORDS = {"开心", "谢谢", "温暖", "感动", "幸福", "喜欢", "爱", "想念"}
_HIGH_INTENSITY_WORDS = {"崩溃", "受不了", "绝望", "不想活", "好累", "算了", "没意思", "去死"}


def _score(text: str, word_set: set[str]) -> float:
    hits = sum(1 for w in word_set if w in text)
    return min(hits / 3.0, 1.0)


class EmotionRecognizer:
    """L1: 基于 Gross 过程模型的情绪阶段检测 + 情绪向量计算。"""

    def __init__(self):
        self._prev_intensity: float = 0.0

    def recognize(self, text: str, context: dict | None = None) -> RecognitionResult:
        ctx = context or {}

        vector = EmotionVector(
            sadness=_score(text, _SADNESS_WORDS),
            anger=_score(text, _ANGER_WORDS),
            anxiety=_score(text, _ANXIETY_WORDS),
            loneliness=_score(text, _LONELINESS_WORDS),
            warmth=_score(text, _WARMTH_WORDS),
        )

        high_hits = sum(1 for w in _HIGH_INTENSITY_WORDS if w in text)
        raw_intensity = vector.intensity() + min(high_hits / 2.0, 0.5)
        intensity = min(raw_intensity, 1.0)

        # 深夜加权
        hour = ctx.get("hour", 12)
        if hour >= 23 or hour < 5:
            intensity = min(intensity + 0.1, 1.0)

        stage = self._classify_stage(intensity)
        self._prev_intensity = intensity

        return RecognitionResult(stage=stage, vector=vector, intensity=intensity)

    def _classify_stage(self, intensity: float) -> EmotionStage:
        """根据当前强度和历史强度判断阶段。"""
        if intensity >= 0.6:
            return EmotionStage.ERUPTION
        if self._prev_intensity >= 0.6 and intensity < 0.6:
            return EmotionStage.RECOVERY
        return EmotionStage.PRE_TRIGGER
