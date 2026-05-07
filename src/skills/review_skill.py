"""ReviewSkill: 关系复盘技能。

帮助用户理性回顾关系，找到成长点而非沉溺。
"""
from openai import OpenAI

from src.config import OPENAI_API_KEY, OPENAI_BASE_URL, MODEL_NAME
from .base import BaseSkill, SkillResult


REVIEW_SYSTEM_PROMPT = """\
你是一位理性温和的关系复盘教练。帮助用户：
1. 客观回顾关系中的关键转折点
2. 识别双方的行为模式（而非归咎某一方）
3. 提炼可迁移的成长经验
4. 温和引导面向未来

回复要求：
- 不评判对错，只分析模式
- 每次聚焦 1-2 个点，不要一次倾倒
- 最后给一个面向未来的小行动建议
"""


class ReviewSkill(BaseSkill):
    name = "relationship_review"
    description = "关系复盘：帮助用户理性回顾和成长"
    intent_keywords = ["复盘", "回顾", "为什么分手", "反思", "总结", "问题出在哪"]
    safety_policy = "review"

    def __init__(self, client: OpenAI | None = None):
        self.client = client or OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )

    def execute(self, user_input: str, context: dict) -> SkillResult:
        memories = context.get("relevant_memories", "")
        messages = [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        ]
        if memories:
            messages.append({"role": "system", "content": f"关系记忆:\n{memories}"})
        messages.append({"role": "user", "content": user_input})

        resp = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.6,
            max_tokens=400,
        )
        return SkillResult(
            success=True,
            content=resp.choices[0].message.content.strip(),
            metadata={"skill": self.name, "tokens": resp.usage.total_tokens},
        )
