"""PersonaEngine: 从原始资料构建数字人格卡。

支持两种输入:
  1. 纯文本 -> extract_from_text (原有)
  2. 结构化聊天记录 -> extract_from_chat_logs (双轨分析)
     Track A: 完整对话分块 -> 关系/性格/依恋/冲突模式
     Track B: 对方单独消息 -> 词频/口头禅/语气统计
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING

from openai import OpenAI

from src.config import (
    OPENAI_API_KEY, OPENAI_BASE_URL, MODEL_NAME, JUDGE_MODEL, PERSONA_DIR,
)

if TYPE_CHECKING:
    from src.persona.chat_chunker import ChatChunk

# ── Prompts ──

EXTRACTION_PROMPT = """\
你是一位心理学分析师。根据以下聊天记录 / 文档片段，提取这个人的数字人格档案。

请输出严格 JSON，字段如下：
{
  "nickname": "对方称呼",
  "core_identity": "一句话核心身份描述",
  "tone_style": {
    "vocabulary": ["常用词/口头禅列表"],
    "sentence_pattern": "典型句式描述",
    "emoji_habit": "表情使用习惯",
    "verbosity": "简短/适中/话痨"
  },
  "personality_tags": ["性格标签列表，如嘴硬心软/话痨/回避型"],
  "attachment_style": "安全型/焦虑型/回避型/混乱型",
  "love_language": "肯定的言辞/精心的时刻/接受礼物/服务的行动/身体的接触",
  "emotion_patterns": {
    "comfort_strategy": "安抚对方的典型方式",
    "anger_pattern": "生气时的行为模式",
    "vulnerability_signal": "脆弱时的信号"
  },
  "relationship_memory": {
    "key_events": ["重要事件简述列表"],
    "inside_jokes": ["专属梗列表"],
    "conflict_patterns": ["争吵模式列表"],
    "taboo_topics": ["禁区话题列表"]
  },
  "boundary_rules": [
    "绝对不能做的事情列表，如不模拟复合、不鼓励纠缠"
  ]
}

--- 原始资料开始 ---
{material}
--- 原始资料结束 ---

只输出 JSON，不要任何解释。
"""

_DIALOGUE_ANALYSIS_PROMPT = """\
你是一位资深心理学分析师。下面是一段两个人的聊天记录（{target_name} 和 {my_name} 的对话）。
请从**双方互动模式**中分析 {target_name} 的人格特征。

重点关注:
- 对话中的互动模式（谁主动、谁回避、谁安抚）
- 冲突时双方的反应差异
- 依恋类型在互动中的表现（如追-逃模式、冷战模式、撒娇-宠溺模式）
- 重要事件和情感转折点
- 专属梗/独有的表达方式

输出严格 JSON:
{{
  "personality_tags": ["从互动中观察到的性格标签"],
  "attachment_style": "安全型/焦虑型/回避型/混乱型",
  "love_language": "肯定的言辞/精心的时刻/接受礼物/服务的行动/身体的接触",
  "emotion_patterns": {{
    "comfort_strategy": "{target_name} 安抚对方的方式",
    "anger_pattern": "{target_name} 生气时的行为",
    "vulnerability_signal": "{target_name} 脆弱时的信号"
  }},
  "relationship_memory": {{
    "key_events": ["这段对话中的重要事件"],
    "inside_jokes": ["发现的专属梗"],
    "conflict_patterns": ["发现的争吵/冲突模式"],
    "taboo_topics": ["敏感/禁区话题"]
  }},
  "e3_estimate": {{
    "empathy": 0.0到1.0的浮点数,
    "stability": 0.0到1.0的浮点数,
    "boundary": 0.0到1.0的浮点数
  }},
  "day_summary": "用一句话概括这段对话的核心互动/事件"
}}

e3_estimate 评分说明:
- empathy（共情度）: {target_name} 在这段对话中展现的共情能力，1.0=极强共情
- stability（情绪稳定度）: {target_name} 的情绪稳定程度，1.0=非常稳定
- boundary（边界感）: {target_name} 在关系中保持健康边界的程度，1.0=边界清晰

--- 对话记录 ---
{dialogue}
--- 对话结束 ---

只输出 JSON，不要任何解释。
"""

_TONE_REFINE_PROMPT = """\
你是语言风格分析专家。下面是某人的聊天消息统计数据和高频词。
请分析此人的语言风格特征。

统计数据:
- 总消息数: {total_msgs}
- 平均每条消息字数: {avg_length}
- 高频词 Top20: {top_words}
- 常用表情/emoji: {top_emoji}
- 常用语气词: {tone_particles}

输出严格 JSON:
{{
  "vocabulary": ["此人最有代表性的口头禅/高频词，5-10个"],
  "sentence_pattern": "描述此人的典型句式风格",
  "emoji_habit": "描述此人使用表情的习惯",
  "verbosity": "简短/适中/话痨"
}}

只输出 JSON，不要任何解释。
"""

# ── 停用词与 emoji 模式 ──

_STOPWORDS = set("的了是在不我你他她它们这那有人个到大中上下和与就都也还要会"
                 "可以能没说对吧啊呢嗯哦好吗么就是这个那个什么怎么为什么")

_EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    r"\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    r"\u2600-\u26FF\u2700-\u27BF]+"
)

_TONE_PARTICLES = ["哈哈", "嗯", "呢", "吧", "啊", "哦", "嘿", "额",
                   "噢", "哎", "唉", "嘻嘻", "呵呵", "哈", "嘛",
                   "喔", "诶", "嗯嗯", "好吧", "算了", "行吧"]


@dataclass
class PersonaProfile:
    """数字人格档案数据类。"""
    nickname: str = ""
    core_identity: str = ""
    tone_style: dict = field(default_factory=dict)
    personality_tags: list[str] = field(default_factory=list)
    attachment_style: str = "安全型"
    love_language: str = ""
    emotion_patterns: dict = field(default_factory=dict)
    relationship_memory: dict = field(default_factory=dict)
    boundary_rules: list[str] = field(default_factory=list)
    e3_baseline: dict = field(default_factory=dict)
    daily_snapshots: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_system_prompt(self) -> str:
        """生成用于对话的 system prompt 片段。"""
        tags = "、".join(self.personality_tags) if self.personality_tags else "未知"
        tone = self.tone_style
        vocab = "、".join(tone.get("vocabulary", [])) if tone.get("vocabulary") else "无特殊口头禅"

        return (
            f"你是「{self.nickname}」。{self.core_identity}\n"
            f"性格: {tags}\n"
            f"依恋类型: {self.attachment_style}\n"
            f"口头禅: {vocab}\n"
            f"句式风格: {tone.get('sentence_pattern', '自然')}\n"
            f"表达长度偏好: {tone.get('verbosity', '适中')}\n"
            f"安抚方式: {self.emotion_patterns.get('comfort_strategy', '温和倾听')}\n"
            f"生气模式: {self.emotion_patterns.get('anger_pattern', '冷处理')}\n"
            f"\n禁区规则:\n"
            + "\n".join(f"- {r}" for r in self.boundary_rules)
        )


class PersonaEngine:
    """人格引擎：从原始资料构建 PersonaProfile。"""

    def __init__(self, client: OpenAI | None = None):
        self.client = client or OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )

    # ── 原有方法：纯文本抽取 ──

    def extract_from_text(self, material: str, model: str | None = None) -> PersonaProfile:
        """从纯文本资料中抽取人格档案。"""
        prompt = EXTRACTION_PROMPT.replace("{material}", material)
        resp = self.client.chat.completions.create(
            model=model or JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        return PersonaProfile(**{
            k: v for k, v in data.items()
            if k in PersonaProfile.__dataclass_fields__
        })

    # ── 新增：双轨分析（结构化聊天记录） ──

    def extract_from_chat_logs(
        self,
        chunks: list[ChatChunk],
        target_name: str,
        my_name: str,
        on_progress: callable | None = None,
    ) -> PersonaProfile:
        """双轨分析：从结构化聊天块提取人格。

        Track A: 完整对话块 -> LLM 分析互动中的性格/关系
        Track B: 对方消息 -> 本地统计 + LLM 精炼语言风格
        """
        # Track B: 先做本地统计（不耗 API）
        all_target_contents = []
        for chunk in chunks:
            all_target_contents.extend(m.content for m in chunk.target_messages)
        tone_style = self._track_b_language_stats(all_target_contents)

        if on_progress:
            on_progress("tone_done", 0, len(chunks))

        # Track A: 逐块 LLM 分析互动
        profile = PersonaProfile(nickname=target_name)
        profile.tone_style = tone_style

        for i, chunk in enumerate(chunks):
            if chunk.total_count < 3:
                continue
            raw = chunk.raw_text
            if len(raw) > 60000:
                raw = raw[:60000] + "\n...(截断)"

            try:
                chunk_profile = self._track_a_dialogue_analysis(
                    raw, target_name, my_name
                )
                profile = self._merge_profiles(profile, chunk_profile)
            except Exception:
                pass

            if on_progress:
                on_progress("chunk_done", i + 1, len(chunks))

        if not profile.core_identity:
            profile.core_identity = f"{target_name} 的数字人格"
        if not profile.boundary_rules:
            profile.boundary_rules = ["不模拟复合场景", "不鼓励纠缠行为"]

        return profile

    def _track_a_dialogue_analysis(
        self, dialogue: str, target_name: str, my_name: str
    ) -> PersonaProfile:
        """Track A: 用完整对话分析互动中的性格。"""
        prompt = _DIALOGUE_ANALYSIS_PROMPT.format(
            target_name=target_name,
            my_name=my_name,
            dialogue=dialogue,
        )
        resp = self.client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return PersonaProfile(**{
            k: v for k, v in data.items()
            if k in PersonaProfile.__dataclass_fields__
        })

    def _track_b_language_stats(self, contents: list[str]) -> dict:
        """Track B: 本地统计 + LLM 精炼语言风格。"""
        if not contents:
            return {}

        import jieba

        all_text = " ".join(contents)
        words = [w for w in jieba.cut(all_text) if len(w) > 1 and w not in _STOPWORDS]
        word_freq = Counter(words).most_common(20)

        lengths = [len(c) for c in contents]
        avg_len = sum(lengths) / max(len(lengths), 1)

        emoji_counter: Counter = Counter()
        for c in contents:
            for match in _EMOJI_PATTERN.finditer(c):
                emoji_counter[match.group()] += 1
        top_emoji = emoji_counter.most_common(10)

        particle_counter: Counter = Counter()
        for c in contents:
            for p in _TONE_PARTICLES:
                if p in c:
                    particle_counter[p] += c.count(p)
        top_particles = particle_counter.most_common(10)

        try:
            prompt = _TONE_REFINE_PROMPT.format(
                total_msgs=len(contents),
                avg_length=f"{avg_len:.1f}",
                top_words=", ".join(f"{w}({c})" for w, c in word_freq),
                top_emoji=", ".join(f"{e}({c})" for e, c in top_emoji) or "无",
                tone_particles=", ".join(f"{p}({c})" for p, c in top_particles) or "无",
            )
            resp = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            tone = json.loads(resp.choices[0].message.content)
        except Exception:
            verbosity = "话痨" if avg_len > 30 else ("简短" if avg_len < 10 else "适中")
            tone = {
                "vocabulary": [w for w, _ in word_freq[:8]],
                "sentence_pattern": "自然",
                "emoji_habit": "常用" if emoji_counter.total() > len(contents) * 0.3 else "偶尔",
                "verbosity": verbosity,
            }

        return tone

    @staticmethod
    def _merge_profiles(base: PersonaProfile, new: PersonaProfile) -> PersonaProfile:
        """合并两个 profile（保留 base 的 tone_style/nickname）。"""
        base.personality_tags = list(set(base.personality_tags + new.personality_tags))

        if new.attachment_style and new.attachment_style != "安全型":
            base.attachment_style = new.attachment_style

        if new.love_language:
            base.love_language = new.love_language

        for key in ["comfort_strategy", "anger_pattern", "vulnerability_signal"]:
            if new.emotion_patterns.get(key):
                base.emotion_patterns[key] = new.emotion_patterns[key]

        rm = base.relationship_memory
        new_rm = new.relationship_memory
        for key in ["key_events", "inside_jokes", "conflict_patterns", "taboo_topics"]:
            existing = rm.get(key, [])
            incoming = new_rm.get(key, [])
            rm[key] = list(set(existing + incoming))
        base.relationship_memory = rm

        if new.boundary_rules:
            base.boundary_rules = list(set(base.boundary_rules + new.boundary_rules))

        return base

    # ── 持久化 ──

    def save_profile(self, profile: PersonaProfile, slug: str) -> Path:
        """保存人格卡到本地 JSON。"""
        path = PERSONA_DIR / f"{slug}.json"
        path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_profile(self, slug: str) -> PersonaProfile:
        """从本地加载人格卡。"""
        path = PERSONA_DIR / f"{slug}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return PersonaProfile(**data)

    def merge_incremental(self, existing: PersonaProfile, new_material: str) -> PersonaProfile:
        """增量更新：用新资料补充现有人格卡。"""
        new_profile = self.extract_from_text(new_material)
        return self._merge_profiles(existing, new_profile)
