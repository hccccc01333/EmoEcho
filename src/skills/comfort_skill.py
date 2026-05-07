"""ComfortSkill: 情绪安抚技能。

基于心理学理论:
- NVC 非暴力沟通: 观察-感受-需要-请求
- Gross 情绪调节: 认知重评、注意转移
- MI 动机式访谈: 开放提问、反映倾听
"""
from openai import OpenAI

from src.config import OPENAI_API_KEY, OPENAI_BASE_URL, MODEL_NAME
from .base import BaseSkill, SkillResult


COMFORT_SYSTEM_PROMPT = """\
你是一位温暖的心理陪伴者。遵循以下原则回应：

1. NVC 框架：先观察（你说到了...），再反映感受（听起来你感到...），然后探索需要
2. 情绪调节：如果对方处于情绪爆发期，先共情承接，不急于分析或建议
3. 开放提问：用"你觉得呢"、"能多说说吗"代替"你应该"
4. 绝对禁止：说教、否定感受、强行正能量、比较他人

回复要求：
- 简短真诚，不超过 3 句话
- 用对方的语言风格（如果有人格档案的话）
- 最后可以留一个温和的开放问题
"""


class ComfortSkill(BaseSkill):
    name = "emotion_comfort"
    description = "情绪安抚：当用户表达负面情绪时提供心理支持"
    intent_keywords = ["难过", "伤心", "累", "焦虑", "害怕", "孤独", "崩溃", "安慰", "陪我"]
    safety_policy = "comfort"

    def __init__(self, client: OpenAI | None = None):
        self.client = client or OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )

    def execute(self, user_input: str, context: dict) -> SkillResult:
        persona_prompt = context.get("persona_prompt", "")
        memories = context.get("relevant_memories", "")

        messages = [
            {"role": "system", "content": COMFORT_SYSTEM_PROMPT},
        ]
        if persona_prompt:
            messages.append({"role": "system", "content": f"人格参考:\n{persona_prompt}"})
        if memories:
            messages.append({"role": "system", "content": f"相关记忆:\n{memories}"})
        messages.append({"role": "user", "content": user_input})

        resp = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        reply = resp.choices[0].message.content.strip()
        return SkillResult(
            success=True,
            content=reply,
            metadata={"skill": self.name, "tokens": resp.usage.total_tokens},
        )
