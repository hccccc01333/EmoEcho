"""BaseSkill: 统一技能协议。

每个 Skill 实现:
  name        - 技能名称
  intent      - 触发意图关键词
  execute()   - 执行逻辑
  safety_policy - 安全约束
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SkillResult:
    """技能执行结果。"""
    success: bool = True
    content: str = ""
    metadata: dict = field(default_factory=dict)


class BaseSkill(ABC):
    """技能基类，所有 Skill 继承此类。"""

    name: str = "base_skill"
    description: str = ""
    intent_keywords: list[str] = []
    safety_policy: str = "default"

    @abstractmethod
    def execute(self, user_input: str, context: dict) -> SkillResult:
        """执行技能，返回结果。"""
        ...

    def match_intent(self, text: str) -> float:
        """计算文本与本技能意图的匹配度 (0~1)。"""
        hits = sum(1 for kw in self.intent_keywords if kw in text)
        return min(hits / max(len(self.intent_keywords), 1), 1.0)
