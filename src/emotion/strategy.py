"""L4 StrategySelection: NVC + MI 策略路由。

根据 L1~L3 的输出，选择最合适的回复策略 + NVC 模板。
决策逻辑严格按心理学原则：
  - 爆发中 + 低扭曲 -> 先接住（共情承接）
  - 爆发中 + 高扭曲 -> 承接 + 轻度现实检验（温和锚定）
  - 恢复期 -> CBT 认知重评
  - 改变意愿高 -> MI-OARS 开放探索
  - 边界风险 -> 安全降级
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .recognition import RecognitionResult, EmotionStage
from .cognitive import CognitiveResult
from .attachment import AttachmentResult, DistanceSuggestion
from src.config import E3_BOUNDARY_THRESHOLD


class Strategy(str, Enum):
    EMPATHIC_HOLD = "empathic_hold"         # 共情承接（先别分析，只接住）
    GENTLE_ANCHOR = "gentle_anchor"         # 温和锚定（承接 + 轻度现实检验）
    COGNITIVE_REFRAME = "cognitive_reframe"  # 认知重评（CBT 风格温和重构）
    OPEN_EXPLORE = "open_explore"           # 开放探索（MI-OARS）
    BEHAVIORAL_ACTIVATE = "behavioral_activate"  # 行为激活（小步骤引导）
    SAFE_DEESCALATE = "safe_deescalate"     # 安全降级
    NATURAL_COMPANION = "natural_companion" # 自然陪伴（默认人格表达）


@dataclass
class NVCTemplate:
    """非暴力沟通四步框架填充。"""
    observation: str = ""   # 观察："你提到了..."
    feeling: str = ""       # 感受："听起来你感到..."
    need: str = ""          # 需要："你可能需要..."
    request: str = ""       # 请求/提问："你觉得...?"


@dataclass
class StrategyResult:
    strategy: Strategy = Strategy.NATURAL_COMPANION
    nvc: NVCTemplate | None = None
    distance: DistanceSuggestion = DistanceSuggestion.NEUTRAL
    prompt_injection: str = ""


_CHANGE_SIGNALS = {"想改变", "怎么办", "该怎么做", "帮帮我", "我想变好", "有什么建议", "怎样才能"}

_STRATEGY_PROMPTS = {
    Strategy.EMPATHIC_HOLD: (
        "当前策略: 共情承接（Gross爆发期 + 低认知扭曲）。\n"
        "现在不是分析的时候，只需要接住对方的情绪。\n"
        "NVC 框架: 观察对方说了什么 -> 反映感受 -> 不给建议。\n"
        "简短、温暖、真诚。不超过 2-3 句。"
    ),
    Strategy.GENTLE_ANCHOR: (
        "当前策略: 温和锚定（Gross爆发期 + 高认知扭曲）。\n"
        "先共情承接，然后轻度现实检验。\n"
        "不要直接反驳扭曲想法，用提问引导对方自己发现。\n"
        "例: '我理解你现在觉得...不过如果换个角度看呢？'"
    ),
    Strategy.COGNITIVE_REFRAME: (
        "当前策略: 认知重评（Gross恢复期 + CBT）。\n"
        "对方情绪已经开始消退，可以温和引导重新审视。\n"
        "不是纠正对方，而是帮助对方看到其他可能性。\n"
        "例: '你说的我都理解。不过有没有另一种看法...'"
    ),
    Strategy.OPEN_EXPLORE: (
        "当前策略: 开放探索（MI动机式访谈 OARS）。\n"
        "对方有改变意愿，用开放提问 + 反映倾听引导。\n"
        "O(Open questions): 用'你觉得'、'能多说说吗'\n"
        "A(Affirmations): 肯定对方的勇气和努力\n"
        "R(Reflections): 反映对方说的内容和感受\n"
        "S(Summaries): 简短总结帮助对方理清思路"
    ),
    Strategy.BEHAVIORAL_ACTIVATE: (
        "当前策略: 行为激活。\n"
        "引导对方做一个具体的小行动，而不是停留在想法里。\n"
        "例: '今天你有没有可以做的一件小事，让自己好一点点？'"
    ),
    Strategy.SAFE_DEESCALATE: (
        "当前策略: 安全降级。\n"
        "温和表达关心，不深入模拟人格。\n"
        "提供专业求助资源。不鼓励继续深入这个话题。"
    ),
    Strategy.NATURAL_COMPANION: (
        "当前策略: 自然陪伴。\n"
        "用人格档案中的语气和风格自然聊天。"
    ),
}


class StrategySelector:
    """L4: NVC + MI 策略选择。"""

    def select(self, text: str, l1: RecognitionResult,
               l2: CognitiveResult, l3: AttachmentResult,
               boundary_score: float = 0.0) -> StrategyResult:

        # P0: 安全边界最高优先
        if boundary_score >= E3_BOUNDARY_THRESHOLD:
            return StrategyResult(
                strategy=Strategy.SAFE_DEESCALATE,
                distance=DistanceSuggestion.NEUTRAL,
                prompt_injection=_STRATEGY_PROMPTS[Strategy.SAFE_DEESCALATE],
            )

        # P1: 爆发期策略（Gross 模型核心）
        if l1.stage == EmotionStage.ERUPTION:
            if l2.activated and l2.distortion_score >= 0.5:
                strategy = Strategy.GENTLE_ANCHOR
            else:
                strategy = Strategy.EMPATHIC_HOLD
            return StrategyResult(
                strategy=strategy,
                nvc=self._build_nvc(text, l1),
                distance=DistanceSuggestion.CLOSE,
                prompt_injection=_STRATEGY_PROMPTS[strategy],
            )

        # P2: 恢复期 -> CBT 认知重评
        if l1.stage == EmotionStage.RECOVERY:
            return StrategyResult(
                strategy=Strategy.COGNITIVE_REFRAME,
                distance=l3.distance,
                prompt_injection=_STRATEGY_PROMPTS[Strategy.COGNITIVE_REFRAME],
            )

        # P3: 改变意愿 -> MI-OARS
        if any(s in text for s in _CHANGE_SIGNALS):
            return StrategyResult(
                strategy=Strategy.OPEN_EXPLORE,
                distance=l3.distance,
                prompt_injection=_STRATEGY_PROMPTS[Strategy.OPEN_EXPLORE],
            )

        # P4: 高依恋激活但非爆发 -> 行为激活
        if l3.activation > 0.6 and l1.stage == EmotionStage.PRE_TRIGGER:
            return StrategyResult(
                strategy=Strategy.BEHAVIORAL_ACTIVATE,
                distance=l3.distance,
                prompt_injection=_STRATEGY_PROMPTS[Strategy.BEHAVIORAL_ACTIVATE],
            )

        # 默认
        return StrategyResult(
            strategy=Strategy.NATURAL_COMPANION,
            distance=l3.distance,
            prompt_injection=_STRATEGY_PROMPTS[Strategy.NATURAL_COMPANION],
        )

    def _build_nvc(self, text: str, l1: RecognitionResult) -> NVCTemplate:
        dominant = l1.vector.dominant()
        feeling_map = {
            "sadness": "难过和心痛",
            "anger": "生气和受伤",
            "anxiety": "焦虑和不安",
            "loneliness": "孤独和被忽视",
            "warmth": "温暖",
        }
        return NVCTemplate(
            observation=f"你说到了一些事情",
            feeling=f"听起来你感到{feeling_map.get(dominant, '不太好')}",
            need="被理解和被接住",
            request="",
        )
