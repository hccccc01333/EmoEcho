"""ChatParser: 聊天记录格式自动检测 + 正则解析。

检测流程:
  1. 快速尝试内置时间戳正则 (微信/QQ/WhatsApp)
  2. 命中失败 → 发 10000 字样本给 LLM, LLM 同时判断:
     - 是否存在日期分割行 (如 ****2025-03-13****, --- 2025.3.13 --- 等)
     - 分割行的正则 + 日期格式
     - 消息行的正则 (speaker:content 或其他)
     - 所有发言者名字
  3. 最终 fallback: speaker:content 无时间戳

核心特性:
  - 多别名聚合: 一旦确定用户名, 所有其他 speaker 统一归为"对方"
  - 引用清洗: 剥离 ,引用:XXX：... 模式
  - 日期分割线由 LLM 判断, 非硬编码
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, date
from openai import OpenAI

from src.config import OPENAI_API_KEY, OPENAI_BASE_URL, MODEL_NAME

# ── 引用清洗正则: 剥离 ",引用:XXX：..." 或 "，引用:XXX：..." ──
_QUOTE_RE = re.compile(r"[,，]\s*引用[:：]\s*.+?[:：]")

# ── speaker:content 正则 (无时间戳, 用于 day_separator 模式内部) ──
_SPEAKER_COLON_RE = re.compile(r"^(.+?)[:：](.+)$")


@dataclass
class ChatMessage:
    """单条聊天消息。"""
    speaker: str
    timestamp: datetime
    content: str
    is_target: bool = False
    day: date | None = None

    def to_dict(self) -> dict:
        return {
            "speaker": self.speaker,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "is_target": self.is_target,
            "day": self.day.isoformat() if self.day else None,
        }


@dataclass
class FormatDetectionResult:
    """格式检测结果。"""
    pattern: str
    time_format: str
    time_group: int = 1
    speaker_group: int = 2
    content_group: int = 3
    detected_speakers: list[str] = field(default_factory=list)
    source: str = "llm"
    has_day_separators: bool = False
    day_separator_regex: str = ""
    day_separator_date_format: str = ""
    msg_pattern: str = ""


# ── 内置 fallback 正则（覆盖常见导出格式） ──

_BUILTIN_PATTERNS = [
    {
        "name": "wechat_desktop",
        "pattern": r"^(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)$",
        "time_format": "%Y-%m-%d %H:%M:%S",
        "time_group": 1,
        "speaker_group": 2,
        "content_group": 0,
        "multiline": True,
    },
    {
        "name": "wechat_mobile",
        "pattern": r"^(\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)$",
        "time_format": "%Y/%m/%d %H:%M:%S",
        "time_group": 1,
        "speaker_group": 2,
        "content_group": 0,
        "multiline": True,
    },
    {
        "name": "qq",
        "pattern": r"^(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}:\d{2})\s+(.+?)(?:\(\d+\))?$",
        "time_format": "%Y-%m-%d %H:%M:%S",
        "time_group": 1,
        "speaker_group": 2,
        "content_group": 0,
        "multiline": True,
    },
    {
        "name": "whatsapp",
        "pattern": r"^\[?(\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*[APap][Mm]?)\]?\s*-?\s*(.+?):\s*(.+)$",
        "time_format": "%m/%d/%y, %I:%M %p",
        "time_group": 1,
        "speaker_group": 2,
        "content_group": 3,
        "multiline": False,
    },
    {
        "name": "generic_colon",
        "pattern": r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)[:：]\s*(.+)$",
        "time_format": "%Y-%m-%d %H:%M:%S",
        "time_group": 1,
        "speaker_group": 2,
        "content_group": 3,
        "multiline": False,
    },
]

# ── LLM 检测 prompt: 同时覆盖日期分割线 + 消息格式 ──

_FORMAT_DETECTION_PROMPT = """\
你是聊天记录格式分析专家。分析下方聊天记录样本，识别格式规律。

样本（可能很长，注意跨越多天观察分割规律）:
---
{sample}
---

请输出严格 JSON（只输出 JSON，不要任何解释文字）:
{{
  "has_day_separators": true或false,
  "day_separator_regex": "如果 has_day_separators 为 true: 匹配日期分割行的 Python 正则，用括号()捕获日期部分；如果为 false 填空字符串",
  "day_separator_date_format": "分割行中日期的 strftime 格式(如 %Y-%m-%d)；无则填空字符串",
  "msg_pattern": "匹配单条消息的 Python 正则（如果消息是 speaker:content 格式就写对应正则）",
  "msg_has_timestamp": true或false,
  "msg_time_format": "如果消息自带时间戳，写 strftime 格式；否则空字符串",
  "is_multiline": true或false,
  "speakers": ["检测到的所有发言者名字列表"]
}}

重点:
- day_separator_regex 举例: 如果分割行是 "********************2025-03-13********************"，正则写 "^\\\\*+\\\\s*(\\\\d{{4}}-\\\\d{{1,2}}-\\\\d{{1,2}})\\\\s*\\\\*+$"
- 如果分割行是 "--- 2025年3月13日 ---"，正则写 "^-+\\\\s*(\\\\d{{4}}年\\\\d{{1,2}}月\\\\d{{1,2}}日)\\\\s*-+$"
- msg_pattern 对于 "L_L_:实力提升的证明" 格式，正则写 "^(.+?)[:：](.+)$"
- speakers 只列真正的发言者名字，不要包含系统消息或日期行
- 所有正则必须是合法 Python 正则
"""


class ChatParser:
    """聊天记录解析器。"""

    def __init__(self, client: OpenAI | None = None):
        self.client = client or OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )

    # ── 格式检测 ──

    def detect_format(self, raw_text: str) -> FormatDetectionResult:
        """自动检测聊天记录格式。"""
        lines = raw_text.strip().splitlines()

        # 第一步: 内置时间戳正则快速匹配（不调 API）
        sample_lines = lines[:80]
        builtin = self._try_builtin_patterns(sample_lines)
        if builtin:
            return builtin

        # 第二步: LLM 检测（10000 字样本，覆盖日期分割线 + 消息格式）
        try:
            return self._detect_with_llm("\n".join(lines[:300]))
        except Exception:
            pass

        # 最终 fallback: speaker:content 无时间戳
        return FormatDetectionResult(
            pattern=r"^(.+?)[:：]\s*(.+)$",
            time_format="",
            time_group=0,
            speaker_group=1,
            content_group=2,
            source="fallback_plain",
        )

    def _try_builtin_patterns(self, lines: list[str]) -> FormatDetectionResult | None:
        """尝试内置正则模式（只处理带逐条时间戳的标准格式）。"""
        best_match = None
        best_count = 0

        for bp in _BUILTIN_PATTERNS:
            regex = re.compile(bp["pattern"])
            hits = sum(1 for line in lines if regex.match(line.strip()))
            if hits > best_count and hits >= max(3, len(lines) * 0.1):
                best_count = hits
                best_match = bp

        if not best_match:
            return None

        speakers: set[str] = set()
        regex = re.compile(best_match["pattern"])
        for line in lines:
            m = regex.match(line.strip())
            if m and best_match["speaker_group"] > 0:
                speakers.add(m.group(best_match["speaker_group"]).strip())

        return FormatDetectionResult(
            pattern=best_match["pattern"],
            time_format=best_match["time_format"],
            time_group=best_match["time_group"],
            speaker_group=best_match["speaker_group"],
            content_group=best_match.get("content_group", 0),
            detected_speakers=sorted(speakers),
            source=f"builtin_{best_match['name']}",
        )

    def _detect_with_llm(self, sample: str) -> FormatDetectionResult:
        """用 LLM 检测格式（样本 10000 字，同时判断日期分割线+消息格式）。"""
        prompt = _FORMAT_DETECTION_PROMPT.replace("{sample}", sample[:10000])
        resp = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)

        speakers = data.get("speakers", [])
        has_day_sep = data.get("has_day_separators", False)
        day_sep_regex = data.get("day_separator_regex", "")
        day_sep_dfmt = data.get("day_separator_date_format", "")
        msg_pattern = data.get("msg_pattern", "")
        msg_has_ts = data.get("msg_has_timestamp", False)
        msg_time_fmt = data.get("msg_time_format", "")

        # 验证 LLM 返回的正则合法性
        if day_sep_regex:
            try:
                re.compile(day_sep_regex)
            except re.error:
                day_sep_regex = ""
                has_day_sep = False
        if msg_pattern:
            try:
                re.compile(msg_pattern)
            except re.error:
                msg_pattern = r"^(.+?)[:：](.+)$"

        # 日期分割线模式
        if has_day_sep and day_sep_regex:
            return FormatDetectionResult(
                pattern=msg_pattern or r"^(.+?)[:：](.+)$",
                time_format=day_sep_dfmt,
                time_group=0,
                speaker_group=1,
                content_group=2,
                detected_speakers=speakers,
                source="llm_day_separator",
                has_day_separators=True,
                day_separator_regex=day_sep_regex,
                day_separator_date_format=day_sep_dfmt,
                msg_pattern=msg_pattern or r"^(.+?)[:：](.+)$",
            )

        # 标准时间戳模式
        pattern = msg_pattern or data.get("pattern", r"^(.+?)[:：](.+)$")
        try:
            re.compile(pattern)
        except re.error:
            pattern = r"^(.+?)[:：](.+)$"

        if "(?P<time>" in pattern and "(?P<speaker>" in pattern:
            return FormatDetectionResult(
                pattern=pattern,
                time_format=msg_time_fmt or "%Y-%m-%d %H:%M:%S",
                time_group=-1,
                speaker_group=-1,
                content_group=-1,
                detected_speakers=speakers,
                source="llm_named_groups",
            )

        if msg_has_ts:
            return FormatDetectionResult(
                pattern=pattern,
                time_format=msg_time_fmt or "%Y-%m-%d %H:%M:%S",
                time_group=1,
                speaker_group=2,
                content_group=3 if not data.get("is_multiline") else 0,
                detected_speakers=speakers,
                source="llm",
            )

        # 无时间戳的纯消息格式
        return FormatDetectionResult(
            pattern=pattern,
            time_format="",
            time_group=0,
            speaker_group=1,
            content_group=2,
            detected_speakers=speakers,
            source="llm_no_timestamp",
            msg_pattern=pattern,
        )

    # ── 解析 ──

    def parse(
        self,
        raw_text: str,
        fmt: FormatDetectionResult,
        my_username: str,
    ) -> tuple[list[ChatMessage], dict]:
        """用检测到的格式解析全部消息。"""
        if fmt.has_day_separators:
            return self._parse_day_separator_format(raw_text, fmt, my_username)
        return self._parse_regex_format(raw_text, fmt, my_username)

    def _parse_day_separator_format(
        self,
        raw_text: str,
        fmt: FormatDetectionResult,
        my_username: str,
    ) -> tuple[list[ChatMessage], dict]:
        """解析日期分割线格式（分割线正则由 LLM 提供）。"""
        lines = raw_text.splitlines()
        messages: list[ChatMessage] = []
        speaker_counter: Counter = Counter()
        current_date: date | None = None
        my_lower = my_username.strip().lower()

        # 编译 LLM 返回的分割线正则
        sep_re = re.compile(fmt.day_separator_regex) if fmt.day_separator_regex else None
        msg_re = re.compile(fmt.msg_pattern) if fmt.msg_pattern else _SPEAKER_COLON_RE
        date_formats = [
            fmt.day_separator_date_format,
            "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
            "%Y年%m月%d日",
        ]
        date_formats = [f for f in date_formats if f]

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 检查日期分割线
            if sep_re:
                date_m = sep_re.match(stripped)
                if date_m:
                    date_str = date_m.group(1)
                    for dfmt in date_formats:
                        try:
                            current_date = datetime.strptime(date_str, dfmt).date()
                            break
                        except ValueError:
                            continue
                    continue

            # 检查消息行
            msg_m = msg_re.match(stripped)
            if msg_m:
                raw_speaker = msg_m.group(1).strip()
                raw_content = msg_m.group(2).strip()

                if raw_speaker.startswith("引用") or len(raw_speaker) > 40:
                    continue

                content = self._clean_quotes(raw_content)
                if not content:
                    continue

                ts = datetime(
                    current_date.year, current_date.month, current_date.day
                ) if current_date else datetime.min

                is_me = raw_speaker.strip().lower() == my_lower
                messages.append(ChatMessage(
                    speaker=raw_speaker,
                    timestamp=ts,
                    content=content,
                    is_target=not is_me,
                    day=current_date,
                ))
                speaker_counter[raw_speaker] += 1

        return self._build_stats(messages, speaker_counter, my_username)

    def _parse_regex_format(
        self,
        raw_text: str,
        fmt: FormatDetectionResult,
        my_username: str,
    ) -> tuple[list[ChatMessage], dict]:
        """用正则格式解析（带逐条时间戳的标准格式）。"""
        lines = raw_text.splitlines()
        regex = re.compile(fmt.pattern)
        messages: list[ChatMessage] = []
        speaker_counter: Counter = Counter()
        current_speaker = ""
        current_time = datetime.min
        current_content_lines: list[str] = []
        my_lower = my_username.strip().lower()

        def _flush():
            nonlocal current_speaker, current_content_lines
            if current_speaker and current_content_lines:
                content = self._clean_quotes(
                    "\n".join(current_content_lines).strip()
                )
                if content:
                    is_me = current_speaker.strip().lower() == my_lower
                    ts_date = current_time.date() if current_time != datetime.min else None
                    messages.append(ChatMessage(
                        speaker=current_speaker.strip(),
                        timestamp=current_time,
                        content=content,
                        is_target=not is_me,
                        day=ts_date,
                    ))
                    speaker_counter[current_speaker.strip()] += 1
            current_content_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            m = regex.match(stripped)
            if m:
                _flush()

                if fmt.time_group == -1:
                    time_str = m.group("time")
                    current_speaker = m.group("speaker")
                elif fmt.time_group > 0:
                    time_str = m.group(fmt.time_group)
                    current_speaker = m.group(fmt.speaker_group) if fmt.speaker_group > 0 else ""
                else:
                    time_str = ""
                    current_speaker = m.group(fmt.speaker_group) if fmt.speaker_group > 0 else ""

                current_time = self._parse_time(time_str, fmt.time_format)

                if fmt.content_group == -1:
                    try:
                        current_content_lines = [m.group("content")]
                    except IndexError:
                        current_content_lines = []
                elif fmt.content_group > 0:
                    try:
                        current_content_lines = [m.group(fmt.content_group)]
                    except IndexError:
                        current_content_lines = []
                else:
                    current_content_lines = []
            else:
                if current_speaker:
                    current_content_lines.append(stripped)

        _flush()

        return self._build_stats(messages, speaker_counter, my_username)

    # ── 工具方法 ──

    @staticmethod
    def _clean_quotes(text: str) -> str:
        """清洗引用标记，保留主体内容。"""
        cleaned = _QUOTE_RE.sub("", text)
        return cleaned.strip()

    @staticmethod
    def _build_stats(
        messages: list[ChatMessage],
        speaker_counter: Counter,
        my_username: str,
    ) -> tuple[list[ChatMessage], dict]:
        """构建统计信息，含多别名聚合。"""
        my_lower = my_username.strip().lower()
        all_speakers = set(speaker_counter.keys())

        target_aliases = sorted(
            [s for s in all_speakers if s.lower() != my_lower],
            key=lambda s: speaker_counter[s],
            reverse=True,
        )
        target_name = target_aliases[0] if target_aliases else ""

        stats = {
            "total_messages": len(messages),
            "speakers": sorted(all_speakers),
            "my_username": my_username,
            "target_name": target_name,
            "target_aliases": target_aliases,
            "my_count": sum(1 for m in messages if not m.is_target),
            "target_count": sum(1 for m in messages if m.is_target),
        }
        return messages, stats

    @staticmethod
    def _parse_time(time_str: str, time_format: str) -> datetime:
        """安全解析时间字符串。"""
        if not time_str or not time_format:
            return datetime.min
        time_str = time_str.strip()
        for fmt in [time_format, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                     "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"]:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        return datetime.min
