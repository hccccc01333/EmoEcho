"""SelfLearner: 可控自学习模块。

三层学习机制:
  L1 会话级 - 实时偏好微调（仅当前会话生效）
  L2 纠正层 - 持久化用户纠正（correction_memory）
  L3 周期性 - 每 N 轮做人格配置同步

核心原则: 学习"表达策略"，不学习"价值边界"。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from src.config import EMA_ALPHA, CORRECTION_PRIORITY, PROFILE_SYNC_INTERVAL
from src.memory.engine import MemoryEngine


_CORRECTION_PATTERNS = [
    (re.compile(r"(?:ta|他|她)不会(?:这[样么]|这种)"), "style_correction"),
    (re.compile(r"别[这那][样么]说"), "style_correction"),
    (re.compile(r"(?:语气|说话).*(?:不像|不对|太)"), "tone_correction"),
    (re.compile(r"(?:记错了|不是这样|搞混了)"), "fact_correction"),
    (re.compile(r"(?:更像|应该是|其实ta会)"), "behavior_correction"),
]

_PREFERENCE_SIGNALS = {
    "positive": ["对", "没错", "就是这样", "哈哈", "好真实", "像"],
    "negative": ["不对", "不像", "太假", "尬", "油腻", "机器人"],
}


@dataclass
class SessionState:
    """单次会话的临时学习状态。"""
    tone_adjustment: float = 0.0      # -1(更冷) ~ 1(更热)
    empathy_adjustment: float = 0.0   # -1(更克制) ~ 1(更投入)
    verbosity_adjustment: float = 0.0 # -1(更简短) ~ 1(更话痨)
    turn_count: int = 0
    corrections_this_session: list = field(default_factory=list)


class SelfLearner:
    """自学习引擎。"""

    def __init__(self, memory: MemoryEngine):
        self.memory = memory
        self.session = SessionState()

    # ── L1: 会话级实时学习 ──

    def observe_turn(self, user_text: str, bot_reply: str, msg_id: str = ""):
        """观察每轮对话，提取学习信号。"""
        self.session.turn_count += 1

        # 检测显式纠正
        correction_type = self._detect_correction(user_text)
        if correction_type:
            self._handle_correction(user_text, bot_reply, correction_type, msg_id)
            return

        # 检测隐式偏好
        sentiment = self._detect_preference(user_text)
        if sentiment != 0:
            self._update_session_preference(sentiment)
            self.memory.add_feedback(
                feedback_type="implicit",
                content=user_text,
                score=sentiment,
                msg_id=msg_id,
            )

        # 触发周期性同步
        if self.session.turn_count % PROFILE_SYNC_INTERVAL == 0:
            self.sync_to_adaptive_profile()

    # ── L2: 纠正记忆 ──

    def _detect_correction(self, text: str) -> str | None:
        for pattern, ctype in _CORRECTION_PATTERNS:
            if pattern.search(text):
                return ctype
        return None

    def _handle_correction(self, user_text: str, bot_reply: str,
                           correction_type: str, msg_id: str):
        """将纠正写入持久化纠正记忆。"""
        self.memory.add_correction(
            trigger_text=bot_reply[:200],
            correction=f"[{correction_type}] 用户说: {user_text}",
            priority=CORRECTION_PRIORITY,
        )
        self.memory.add_feedback(
            feedback_type=correction_type,
            content=user_text,
            score=-1.0,
            msg_id=msg_id,
        )
        self.session.corrections_this_session.append({
            "type": correction_type,
            "user_said": user_text,
        })

    # ── 偏好检测 ──

    def _detect_preference(self, text: str) -> float:
        pos = sum(1 for w in _PREFERENCE_SIGNALS["positive"] if w in text)
        neg = sum(1 for w in _PREFERENCE_SIGNALS["negative"] if w in text)
        if pos > neg:
            return min(pos * 0.3, 1.0)
        elif neg > pos:
            return max(-neg * 0.3, -1.0)
        return 0.0

    def _update_session_preference(self, signal: float):
        """EMA 更新会话偏好。"""
        alpha = EMA_ALPHA
        self.session.tone_adjustment = (
            (1 - alpha) * self.session.tone_adjustment + alpha * signal
        )

    # ── L3: 周期性同步 ──

    def sync_to_adaptive_profile(self):
        """将累计偏好写入 adaptive_profile 表。"""
        current_tone = float(self.memory.get_adaptive("tone_pref", "0.0"))
        new_tone = (1 - EMA_ALPHA) * current_tone + EMA_ALPHA * self.session.tone_adjustment
        self.memory.set_adaptive("tone_pref", str(round(new_tone, 4)))

        current_empathy = float(self.memory.get_adaptive("empathy_level", "0.5"))
        new_empathy = (1 - EMA_ALPHA) * current_empathy + EMA_ALPHA * (0.5 + self.session.empathy_adjustment)
        self.memory.set_adaptive("empathy_level", str(round(new_empathy, 4)))

        self.memory.set_adaptive("total_turns", str(self.session.turn_count))

    def get_learning_context(self) -> dict:
        """返回当前学习状态，供 Orchestrator 注入 prompt。"""
        corrections = self.memory.get_active_corrections()
        return {
            "session_tone": round(self.session.tone_adjustment, 3),
            "session_empathy": round(self.session.empathy_adjustment, 3),
            "session_verbosity": round(self.session.verbosity_adjustment, 3),
            "active_corrections": corrections[:5],
            "turn_count": self.session.turn_count,
        }

    def reset_session(self):
        """重置会话状态（新会话时调用）。"""
        self.sync_to_adaptive_profile()
        self.session = SessionState()
