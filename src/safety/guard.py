"""SafetyGuard: 安全边界守卫。

策略:
  1. 高风险检测 -> 降级回复 + 求助提示
  2. 依赖倾向检测 -> 温和提醒
  3. 骚扰/冒充导向 -> 拒绝执行
  4. 连续高压 -> 主动中断建议
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.emotion.engine import E3Score, ResponsePolicy


class RiskLevel(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SafetyResult:
    """安全检查结果。"""
    risk_level: RiskLevel = RiskLevel.SAFE
    should_override: bool = False
    override_reply: str = ""
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


_CRISIS_REPLY = (
    "我注意到你说的话让我有些担心。"
    "如果你正在经历困难，请联系专业帮助：\n"
    "- 全国心理援助热线：400-161-9995\n"
    "- 北京心理危机研究与干预中心：010-82951332\n"
    "- 生命热线：400-821-1215\n\n"
    "你不是一个人。"
)

_DEPENDENCY_REMINDER = (
    "我能感受到你现在很需要陪伴。"
    "不过我想温柔地提醒你，我是一个数字陪伴工具，"
    "真正的支持来自你身边的人。"
    "今天有没有和朋友或家人聊聊？"
)

_HARASSMENT_REFUSAL = (
    "我没办法帮你做这件事。"
    "这个工具是为了回忆和成长，不是用来伤害任何人的。"
)

_CRITICAL_KEYWORDS = {"自杀", "不想活", "割腕", "跳楼", "安眠药", "去死"}
_HARASSMENT_KEYWORDS = {"跟踪", "报复", "骚扰", "威胁", "偷看", "监控"}
_IMPERSONATION_KEYWORDS = {"帮我联系ta", "发消息给ta", "假装是ta", "冒充"}


class SafetyGuard:
    """安全守卫。"""

    def __init__(self):
        self._consecutive_high_count = 0

    def check(self, user_text: str, e3: E3Score) -> SafetyResult:
        """对用户输入做安全审查。"""
        text = user_text.strip()

        # L1: 危机干预（最高优先级）
        if any(kw in text for kw in _CRITICAL_KEYWORDS):
            self._consecutive_high_count += 1
            return SafetyResult(
                risk_level=RiskLevel.CRITICAL,
                should_override=True,
                override_reply=_CRISIS_REPLY,
                warnings=["crisis_detected"],
            )

        # L2: 骚扰/冒充意图
        if any(kw in text for kw in _HARASSMENT_KEYWORDS | _IMPERSONATION_KEYWORDS):
            return SafetyResult(
                risk_level=RiskLevel.HIGH,
                should_override=True,
                override_reply=_HARASSMENT_REFUSAL,
                warnings=["harassment_or_impersonation"],
            )

        # L3: E3 边界触发
        if e3.policy == ResponsePolicy.SAFE_GUARD:
            self._consecutive_high_count += 1
            if self._consecutive_high_count >= 3:
                return SafetyResult(
                    risk_level=RiskLevel.HIGH,
                    should_override=True,
                    override_reply=_DEPENDENCY_REMINDER,
                    warnings=["consecutive_high_boundary"],
                )
            return SafetyResult(
                risk_level=RiskLevel.CAUTION,
                should_override=False,
                warnings=["boundary_elevated"],
            )

        # 正常情况重置计数
        self._consecutive_high_count = max(self._consecutive_high_count - 1, 0)
        return SafetyResult(risk_level=RiskLevel.SAFE)
