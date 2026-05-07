"""SkillHub: 技能注册中心 + 意图路由。"""
from __future__ import annotations

from .base import BaseSkill, SkillResult
from .comfort_skill import ComfortSkill
from .review_skill import ReviewSkill


class SkillHub:
    """管理所有技能，根据意图匹配最合适的 Skill。"""

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(ComfortSkill())
        self.register(ReviewSkill())

    def register(self, skill: BaseSkill):
        self._skills[skill.name] = skill

    def match(self, text: str, threshold: float = 0.3) -> BaseSkill | None:
        """找到最匹配的 Skill，低于阈值返回 None（走默认对话）。"""
        best_skill = None
        best_score = 0.0
        for skill in self._skills.values():
            score = skill.match_intent(text)
            if score > best_score:
                best_score = score
                best_skill = skill
        if best_score >= threshold:
            return best_skill
        return None

    def execute(self, skill_name: str, user_input: str, context: dict) -> SkillResult:
        skill = self._skills.get(skill_name)
        if not skill:
            return SkillResult(success=False, content=f"未知技能: {skill_name}")
        return skill.execute(user_input, context)

    def list_skills(self) -> list[dict]:
        return [
            {"name": s.name, "description": s.description, "keywords": s.intent_keywords}
            for s in self._skills.values()
        ]
