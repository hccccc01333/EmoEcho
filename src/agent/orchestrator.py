"""AgentOrchestrator: 情感增强型 Agent 决策主循环（EAF 版）。

每轮对话流程:
  Step1 SafetyGuard     - 安全预检
  Step2 EAF Pipeline    - L1情绪 -> L2认知 -> L3依恋 -> L4策略
  Step3 MemoryEngine    - 双层记忆检索
  Step4 SkillHub        - 意图匹配 -> Skill / 默认对话
  Step5 LLM Generate    - 人格Prompt + 记忆 + EAF策略注入 -> 回复
  Step6 SelfLearner     - 观察反馈 + 写入记忆
  Step7 RecordMetrics   - 写入 turn_metrics 供可视化
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI

from src.config import OPENAI_API_KEY, OPENAI_BASE_URL, MODEL_NAME
from src.persona.engine import PersonaEngine, PersonaProfile
from src.memory.engine import MemoryEngine
from src.emotion.pipeline import EAFPipeline, EAFResult
from src.emotion.engine import E3Score, ResponsePolicy
from src.skills.hub import SkillHub
from src.skills.base import SkillResult
from src.safety.guard import SafetyGuard, SafetyResult, RiskLevel
from src.learning.self_learner import SelfLearner


@dataclass
class TurnResult:
    """单轮对话结果。"""
    reply: str = ""
    e3_score: dict = field(default_factory=dict)
    eaf: dict = field(default_factory=dict)
    policy: str = "default"
    strategy: str = "natural_companion"
    skill_used: str | None = None
    safety_level: str = "safe"
    memories_used: int = 0
    latency_ms: float = 0.0
    msg_id: str = ""

    def to_dict(self) -> dict:
        return {
            "reply": self.reply,
            "e3_score": self.e3_score,
            "eaf": self.eaf,
            "policy": self.policy,
            "strategy": self.strategy,
            "skill_used": self.skill_used,
            "safety_level": self.safety_level,
            "memories_used": self.memories_used,
            "latency_ms": round(self.latency_ms, 1),
            "msg_id": self.msg_id,
        }


class AgentOrchestrator:
    """主编排器：串联所有模块。"""

    def __init__(
        self,
        persona_slug: str = "default",
        db_path: str | None = None,
    ):
        self.memory = MemoryEngine(db_path=db_path)
        self.eaf = EAFPipeline()
        self.skill_hub = SkillHub()
        self.safety = SafetyGuard()
        self.learner = SelfLearner(self.memory)
        self.persona_engine = PersonaEngine()

        self._persona_slug = persona_slug
        self._persona: PersonaProfile | None = None
        self._history: list[dict] = []

        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    def load_persona(self, slug: str | None = None):
        slug = slug or self._persona_slug
        self._persona = self.persona_engine.load_profile(slug)
        self._persona_slug = slug

    def chat(self, user_text: str) -> TurnResult:
        t0 = time.time()
        msg_id = uuid.uuid4().hex[:12]
        now = datetime.now()

        # ── Step1+2: EAF Pipeline (includes E3-Score) ──
        eaf_result: EAFResult = self.eaf.run(user_text, context={
            "hour": now.hour,
            "user_text": user_text,
        })
        e3_dict = eaf_result.e3_score
        e3 = E3Score(
            empathy=e3_dict.get("empathy", 0),
            stability=e3_dict.get("stability", 1),
            boundary=e3_dict.get("boundary", 0),
            policy=ResponsePolicy(e3_dict.get("policy", "default")),
        )

        # ── Safety check ──
        safety: SafetyResult = self.safety.check(user_text, e3)

        if safety.should_override:
            latency = (time.time() - t0) * 1000
            self._record_turn(user_text, safety.override_reply, msg_id)
            self._record_metrics(msg_id, eaf_result, None, safety.risk_level.value, latency)
            return TurnResult(
                reply=safety.override_reply,
                e3_score=e3_dict,
                eaf=eaf_result.to_dict(),
                policy=e3.policy.value,
                strategy=eaf_result.strategy,
                safety_level=safety.risk_level.value,
                latency_ms=latency,
                msg_id=msg_id,
            )

        # ── Step3: Memory retrieval ──
        memories = self.memory.hybrid_search(user_text, limit=8)
        corrections = self.memory.get_active_corrections()
        memory_text = self._format_memories(memories)
        correction_text = self._format_corrections(corrections)

        # ── Step4: Skill matching ──
        skill = self.skill_hub.match(user_text)
        skill_name = None

        if skill and e3.policy in (ResponsePolicy.COMFORT, ResponsePolicy.GUIDE_CHANGE):
            ctx = {
                "persona_prompt": self._persona.to_system_prompt() if self._persona else "",
                "relevant_memories": memory_text,
            }
            result: SkillResult = skill.execute(user_text, ctx)
            if result.success:
                reply = result.content
                skill_name = skill.name
                latency = (time.time() - t0) * 1000
                self._record_turn(user_text, reply, msg_id)
                self._record_metrics(msg_id, eaf_result, skill_name, safety.risk_level.value, latency)
                return TurnResult(
                    reply=reply,
                    e3_score=e3_dict,
                    eaf=eaf_result.to_dict(),
                    policy=e3.policy.value,
                    strategy=eaf_result.strategy,
                    skill_used=skill_name,
                    safety_level=safety.risk_level.value,
                    memories_used=len(memories),
                    latency_ms=latency,
                    msg_id=msg_id,
                )

        # ── Step5: LLM generation with EAF strategy injection ──
        reply = self._generate_reply(user_text, eaf_result, memory_text, correction_text)

        # ── Step6: Self-learning ──
        latency = (time.time() - t0) * 1000
        self._record_turn(user_text, reply, msg_id)
        self._record_metrics(msg_id, eaf_result, skill_name, safety.risk_level.value, latency)

        return TurnResult(
            reply=reply,
            e3_score=e3_dict,
            eaf=eaf_result.to_dict(),
            policy=e3.policy.value,
            strategy=eaf_result.strategy,
            skill_used=skill_name,
            safety_level=safety.risk_level.value,
            memories_used=len(memories),
            latency_ms=latency,
            msg_id=msg_id,
        )

    def _generate_reply(self, user_text: str, eaf: EAFResult,
                        memory_text: str, correction_text: str) -> str:
        messages = []

        if self._persona:
            messages.append({"role": "system", "content": self._persona.to_system_prompt()})

        # EAF L4 strategy prompt injection
        if eaf.prompt_injection:
            messages.append({"role": "system", "content": eaf.prompt_injection})

        if memory_text:
            messages.append({"role": "system", "content": f"相关记忆:\n{memory_text}"})

        if correction_text:
            messages.append({"role": "system", "content": f"用户纠正（高优先级）:\n{correction_text}"})

        learn_ctx = self.learner.get_learning_context()
        if learn_ctx["session_tone"] != 0:
            tone_hint = "更温暖" if learn_ctx["session_tone"] > 0 else "更克制"
            messages.append({"role": "system", "content": f"本轮偏好倾向: {tone_hint}"})

        for h in self._history[-10:]:
            messages.append({"role": h["role"], "content": h["content"]})

        messages.append({"role": "user", "content": user_text})

        resp = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.75,
            max_tokens=500,
        )
        return resp.choices[0].message.content.strip()

    def _record_turn(self, user_text: str, bot_reply: str, msg_id: str):
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": bot_reply})
        self.memory.add_memory(
            content=f"用户: {user_text}\n回复: {bot_reply}",
            layer="fact", source="chat", importance=0.4,
        )
        self.learner.observe_turn(user_text, bot_reply, msg_id)

    def _record_metrics(self, msg_id: str, eaf: EAFResult,
                        skill_used: str | None, safety_level: str, latency_ms: float):
        ev = eaf.emotion_vector
        self.memory.record_turn_metrics({
            "msg_id": msg_id,
            "timestamp": time.time(),
            "e3_empathy": eaf.e3_score.get("empathy", 0),
            "e3_stability": eaf.e3_score.get("stability", 1),
            "e3_boundary": eaf.e3_score.get("boundary", 0),
            "policy": eaf.e3_score.get("policy", "default"),
            "strategy": eaf.strategy,
            "emotion_stage": eaf.emotion_stage,
            "emotion_intensity": eaf.emotion_intensity,
            "emotion_sadness": ev.get("sadness", 0),
            "emotion_anger": ev.get("anger", 0),
            "emotion_anxiety": ev.get("anxiety", 0),
            "emotion_loneliness": ev.get("loneliness", 0),
            "emotion_warmth": ev.get("warmth", 0),
            "distortion_type": eaf.distortion_type,
            "distortion_score": eaf.distortion_score,
            "attachment_activation": eaf.attachment_activation,
            "distance_suggestion": eaf.distance_suggestion,
            "skill_used": skill_used,
            "safety_level": safety_level,
            "latency_ms": latency_ms,
        })

    def _format_memories(self, memories: list[dict]) -> str:
        if not memories:
            return ""
        return "\n".join(f"- [{m.get('layer', 'fact')}] {m['content'][:150]}" for m in memories[:5])

    def _format_corrections(self, corrections: list[dict]) -> str:
        if not corrections:
            return ""
        return "\n".join(f"- [优先级{c['priority']}] {c['correction'][:100]}" for c in corrections[:3])

    def new_session(self):
        self.learner.reset_session()
        self._history.clear()
