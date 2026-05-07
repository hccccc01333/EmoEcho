"""ChatChunker: 按天统计发言数 + 智能分块。

分块规则:
  - 利用 ChatMessage.day 或 timestamp.date() 分组
  - 日发言总数 <= LOW_ACTIVITY_THRESHOLD (默认10) -> "低活跃日" -> 块边界
  - 日发言总数 == 0 -> 跳过
  - 连续高活跃日 -> 合并为一个 ChatChunk
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from src.persona.chat_parser import ChatMessage

LOW_ACTIVITY_THRESHOLD = 10


@dataclass
class DayStat:
    """单天统计。"""
    day: date
    total: int = 0
    my_count: int = 0
    target_count: int = 0
    messages: list[ChatMessage] = field(default_factory=list)

    @property
    def is_low_activity(self) -> bool:
        return self.total <= LOW_ACTIVITY_THRESHOLD

    def to_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "total": self.total,
            "my_count": self.my_count,
            "target_count": self.target_count,
            "is_low_activity": self.is_low_activity,
        }


@dataclass
class ChatChunk:
    """一个对话块：连续高活跃日合并而成。"""
    date_start: date
    date_end: date
    messages: list[ChatMessage] = field(default_factory=list)
    total_count: int = 0
    day_count: int = 0

    @property
    def raw_text(self) -> str:
        """还原为可读的对话文本，保留双方交互。"""
        lines = []
        current_date = None
        for m in self.messages:
            msg_date = m.day or (m.timestamp.date() if m.timestamp != datetime.min else None)
            if msg_date and msg_date != current_date:
                current_date = msg_date
                lines.append(f"\n--- {current_date.isoformat()} ---")
            lines.append(f"{m.speaker}: {m.content}")
        return "\n".join(lines)

    @property
    def target_messages(self) -> list[ChatMessage]:
        return [m for m in self.messages if m.is_target]

    @property
    def my_messages(self) -> list[ChatMessage]:
        return [m for m in self.messages if not m.is_target]

    def to_dict(self) -> dict:
        return {
            "date_start": self.date_start.isoformat(),
            "date_end": self.date_end.isoformat(),
            "total_count": self.total_count,
            "day_count": self.day_count,
            "target_msg_count": len(self.target_messages),
            "my_msg_count": len(self.my_messages),
        }


def _get_msg_date(m: ChatMessage) -> date:
    """从 ChatMessage 获取日期，优先 .day 字段。"""
    if m.day:
        return m.day
    if m.timestamp and m.timestamp != datetime.min:
        return m.timestamp.date()
    return date.min


class ChatChunker:
    """智能分块器。"""

    def __init__(self, threshold: int = LOW_ACTIVITY_THRESHOLD):
        self.threshold = threshold

    def compute_daily_stats(self, messages: list[ChatMessage]) -> list[DayStat]:
        """按天统计发言数。"""
        day_map: dict[date, DayStat] = {}
        for m in messages:
            d = _get_msg_date(m)
            if d not in day_map:
                day_map[d] = DayStat(day=d)
            stat = day_map[d]
            stat.total += 1
            if m.is_target:
                stat.target_count += 1
            else:
                stat.my_count += 1
            stat.messages.append(m)

        return sorted(day_map.values(), key=lambda s: s.day)

    def chunk(self, messages: list[ChatMessage]) -> list[ChatChunk]:
        """将消息按天分块，低活跃日作为块边界。"""
        daily = self.compute_daily_stats(messages)
        if not daily:
            return []

        chunks: list[ChatChunk] = []
        current_msgs: list[ChatMessage] = []
        current_start: date | None = None
        current_end: date | None = None
        current_days = 0

        def _flush():
            nonlocal current_msgs, current_start, current_end, current_days
            if current_msgs and current_start and current_end:
                chunks.append(ChatChunk(
                    date_start=current_start,
                    date_end=current_end,
                    messages=current_msgs,
                    total_count=len(current_msgs),
                    day_count=current_days,
                ))
            current_msgs = []
            current_start = None
            current_end = None
            current_days = 0

        for stat in daily:
            if stat.total == 0:
                continue

            if stat.is_low_activity:
                _flush()
                if stat.messages:
                    chunks.append(ChatChunk(
                        date_start=stat.day,
                        date_end=stat.day,
                        messages=stat.messages,
                        total_count=stat.total,
                        day_count=1,
                    ))
            else:
                if current_start is None:
                    current_start = stat.day
                current_end = stat.day
                current_msgs.extend(stat.messages)
                current_days += 1

        _flush()

        return chunks

    def chunk_by_day(self, messages: list[ChatMessage]) -> list[ChatChunk]:
        """按天严格分块（每天一个 chunk），用于流式逐天分析。"""
        daily = self.compute_daily_stats(messages)
        chunks: list[ChatChunk] = []
        for stat in daily:
            if stat.total == 0:
                continue
            chunks.append(ChatChunk(
                date_start=stat.day,
                date_end=stat.day,
                messages=stat.messages,
                total_count=stat.total,
                day_count=1,
            ))
        return chunks

    def get_preview(self, messages: list[ChatMessage]) -> dict:
        """返回预览数据（不含完整消息），用于前端确认。"""
        daily = self.compute_daily_stats(messages)
        chunks = self.chunk(messages)
        return {
            "daily_stats": [s.to_dict() for s in daily if s.total > 0],
            "chunk_count": len(chunks),
            "chunks_preview": [c.to_dict() for c in chunks],
            "total_messages": sum(s.total for s in daily),
            "total_days": len([s for s in daily if s.total > 0]),
            "active_days": len([s for s in daily if not s.is_low_activity]),
        }
