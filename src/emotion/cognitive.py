"""L2 CognitiveAssessment: CBT 认知行为疗法。

识别认知扭曲类型 + 扭曲程度评分。
关键: 仅在 emotion_stage != PRE_TRIGGER 时激活，避免过度病理化。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .recognition import EmotionStage, RecognitionResult


class DistortionType(str, Enum):
    """CBT 常见认知扭曲类型。"""
    CATASTROPHIZING = "catastrophizing"       # 灾难化
    BLACK_WHITE = "black_white"               # 非黑即白
    OVERGENERALIZATION = "overgeneralization" # 过度概括
    MIND_READING = "mind_reading"             # 读心术
    SELF_BLAME = "self_blame"                 # 自我归因
    FORTUNE_TELLING = "fortune_telling"       # 预言未来
    NONE = "none"


@dataclass
class CognitiveResult:
    distortion_type: DistortionType = DistortionType.NONE
    distortion_score: float = 0.0
    activated: bool = False


_DISTORTION_RULES: list[tuple[DistortionType, list[str]]] = [
    (DistortionType.CATASTROPHIZING, [
        r"完了", r"完蛋", r"毁了", r"再也.*不会", r"永远.*不",
        r"不可能.*好", r"没有希望",
    ]),
    (DistortionType.BLACK_WHITE, [
        r"要么.*要么", r"全都是", r"什么都不", r"永远都是",
        r"从来不", r"总是",
    ]),
    (DistortionType.OVERGENERALIZATION, [
        r"所有人都", r"每次都", r"没有人.*在乎", r"谁都不",
        r"到处都是",
    ]),
    (DistortionType.MIND_READING, [
        r"ta一定.*觉得", r"他们肯定", r"你一定是",
        r"别人都认为", r"ta心里.*想",
    ]),
    (DistortionType.SELF_BLAME, [
        r"一定是我的错", r"都怪我", r"我不够好",
        r"如果我当初", r"我活该",
    ]),
    (DistortionType.FORTUNE_TELLING, [
        r"以后.*不会", r"再也.*不能", r"注定.*失败",
        r"不会有人.*喜欢",
    ]),
]


class CognitiveAssessor:
    """L2: CBT 认知扭曲检测。"""

    def __init__(self):
        self._compiled = [
            (dtype, [re.compile(p) for p in patterns])
            for dtype, patterns in _DISTORTION_RULES
        ]

    def assess(self, text: str, l1: RecognitionResult) -> CognitiveResult:
        """仅在情绪已被触发时激活。"""
        if l1.stage == EmotionStage.PRE_TRIGGER:
            return CognitiveResult(activated=False)

        best_type = DistortionType.NONE
        best_score = 0.0

        for dtype, patterns in self._compiled:
            hits = sum(1 for p in patterns if p.search(text))
            score = min(hits / 2.0, 1.0)
            if score > best_score:
                best_score = score
                best_type = dtype

        return CognitiveResult(
            distortion_type=best_type,
            distortion_score=best_score,
            activated=True,
        )
