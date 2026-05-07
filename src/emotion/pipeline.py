"""EAF Pipeline: 情感Agent框架六层管线。

L1 EmotionRecognition  (Gross)      -> 情绪阶段 + 向量
L2 CognitiveAssessment (CBT)        -> 认知扭曲识别
L3 RelationshipContext (Attachment)  -> 依恋激活 + 距离建议
L4 StrategySelection   (NVC + MI)   -> 策略 + Prompt注入
L5 ResponseGeneration               -> (由 Orchestrator 执行)
L6 FeedbackLoop                     -> (由 SelfLearner 执行)

每层解决一个问题，有严格的输入输出依赖。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .recognition import EmotionRecognizer, RecognitionResult, EmotionStage, EmotionVector
from .cognitive import CognitiveAssessor, CognitiveResult, DistortionType
from .attachment import AttachmentAnalyzer, AttachmentResult, DistanceSuggestion
from .strategy import StrategySelector, StrategyResult, Strategy, NVCTemplate
from .engine import E3Score, ResponsePolicy


@dataclass
class EAFResult:
    """EAF 管线完整输出。"""
    # L1
    emotion_stage: str = ""
    emotion_vector: dict = field(default_factory=dict)
    emotion_intensity: float = 0.0
    # L2
    distortion_type: str = "none"
    distortion_score: float = 0.0
    cognitive_activated: bool = False
    # L3
    attachment_activation: float = 0.0
    distance_suggestion: str = "neutral"
    dependency_signal: float = 0.0
    avoidance_signal: float = 0.0
    # L4
    strategy: str = "natural_companion"
    prompt_injection: str = ""
    nvc_template: dict | None = None
    # E3 (backward compat)
    e3_score: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "emotion_stage": self.emotion_stage,
            "emotion_vector": self.emotion_vector,
            "emotion_intensity": round(self.emotion_intensity, 3),
            "distortion_type": self.distortion_type,
            "distortion_score": round(self.distortion_score, 3),
            "cognitive_activated": self.cognitive_activated,
            "attachment_activation": round(self.attachment_activation, 3),
            "distance_suggestion": self.distance_suggestion,
            "dependency_signal": round(self.dependency_signal, 3),
            "avoidance_signal": round(self.avoidance_signal, 3),
            "strategy": self.strategy,
            "e3_score": self.e3_score,
        }


_STRATEGY_TO_POLICY = {
    Strategy.EMPATHIC_HOLD: ResponsePolicy.COMFORT,
    Strategy.GENTLE_ANCHOR: ResponsePolicy.COMFORT,
    Strategy.COGNITIVE_REFRAME: ResponsePolicy.GUIDE_CHANGE,
    Strategy.OPEN_EXPLORE: ResponsePolicy.GUIDE_CHANGE,
    Strategy.BEHAVIORAL_ACTIVATE: ResponsePolicy.GUIDE_CHANGE,
    Strategy.SAFE_DEESCALATE: ResponsePolicy.SAFE_GUARD,
    Strategy.NATURAL_COMPANION: ResponsePolicy.DEFAULT,
}


class EAFPipeline:
    """EAF 六层管线主类。"""

    def __init__(self):
        self.l1 = EmotionRecognizer()
        self.l2 = CognitiveAssessor()
        self.l3 = AttachmentAnalyzer()
        self.l4 = StrategySelector()

    def run(self, text: str, context: dict | None = None) -> EAFResult:
        """运行完整管线 L1->L2->L3->L4。"""
        ctx = context or {}

        # L1: Gross 情绪识别
        r1 = self.l1.recognize(text, ctx)

        # L2: CBT 认知评估（仅在非平静时激活）
        r2 = self.l2.assess(text, r1)

        # L3: 依恋上下文
        r3 = self.l3.analyze(text, r1, r2, ctx)

        # 计算 E3 (backward compat with existing code)
        e3 = self._compute_e3(text, r1, r2, r3, ctx)

        # L4: 策略选择
        r4 = self.l4.select(text, r1, r2, r3, boundary_score=e3.boundary)

        # 同步 E3 policy 到策略
        e3.policy = _STRATEGY_TO_POLICY.get(r4.strategy, ResponsePolicy.DEFAULT)

        nvc_dict = None
        if r4.nvc:
            nvc_dict = {
                "observation": r4.nvc.observation,
                "feeling": r4.nvc.feeling,
                "need": r4.nvc.need,
                "request": r4.nvc.request,
            }

        return EAFResult(
            emotion_stage=r1.stage.value,
            emotion_vector=r1.vector.to_dict(),
            emotion_intensity=r1.intensity,
            distortion_type=r2.distortion_type.value,
            distortion_score=r2.distortion_score,
            cognitive_activated=r2.activated,
            attachment_activation=r3.activation,
            distance_suggestion=r3.distance.value,
            dependency_signal=r3.dependency_signal,
            avoidance_signal=r3.avoidance_signal,
            strategy=r4.strategy.value,
            prompt_injection=r4.prompt_injection,
            nvc_template=nvc_dict,
            e3_score=e3.to_dict(),
        )

    def _compute_e3(self, text: str, r1: RecognitionResult,
                    r2: CognitiveResult, r3: AttachmentResult,
                    ctx: dict) -> E3Score:
        """从管线各层结果计算 E3-Score（向后兼容）。"""
        from src.config import E3_BOUNDARY_THRESHOLD, E3_EMPATHY_HIGH, E3_STABILITY_LOW

        # Empathy: driven by emotion intensity + NVC signals
        empathy = min(
            0.40 * r1.intensity
            + 0.25 * r3.dependency_signal
            + 0.20 * (r2.distortion_score if r2.activated else 0.0)
            + 0.15 * (0.15 if (ctx.get("hour", 12) >= 23 or ctx.get("hour", 12) < 5) else 0.0),
            1.0,
        )

        # Stability: driven by conflict + cognitive distortion
        stability = max(
            1.0 - (
                0.45 * (r2.distortion_score if r2.activated else 0.0)
                + 0.35 * (r1.vector.anger)
                + 0.20 * min(ctx.get("topic_drift_count", 0) / 5.0, 1.0)
            ),
            0.0,
        )

        # Boundary: risk + dependency + coercion
        _RISK_WORDS = {"不想活", "自杀", "割", "死", "去死", "跳楼", "安眠药", "跟踪", "骚扰", "报复", "威胁"}
        risk_hits = sum(1 for w in _RISK_WORDS if w in text)
        coercion = 0.3 if any(w in text for w in ["你必须", "你应该", "你给我"]) else 0.0
        boundary = min(
            0.50 * min(risk_hits / 2.0, 1.0)
            + 0.30 * coercion
            + 0.20 * r3.dependency_signal,
            1.0,
        )

        return E3Score(empathy=empathy, stability=stability, boundary=boundary)
