"""StreamExtractor: 逐天流式人格提取。

流程:
  1. 解析全文 → 按日期分段（复用 ChatParser + ChatChunker）
  2. 对每天调用 Track A 分析 → merge 进 running PersonaProfile
  3. 每天 yield 一个 DailySnapshot（日期 + 新增 tags + 累积 E3 + 摘要）
  4. 全部完成后跑 Track B（语言统计），merge 进最终 profile
  5. yield 完成事件 + 最终 profile
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import AsyncGenerator

from src.config import PERSONA_DIR
from src.persona.engine import PersonaEngine, PersonaProfile
from src.persona.chat_parser import ChatParser
from src.persona.chat_chunker import ChatChunker


@dataclass
class DailySnapshot:
    """单日分析快照。"""
    day: str
    day_summary: str = ""
    new_tags: list[str] | None = None
    e3_estimate: dict | None = None
    cumulative_tags: list[str] | None = None
    cumulative_e3: dict | None = None
    message_count: int = 0
    target_msg_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class StreamExtractor:
    """逐天流式人格提取器。"""

    def __init__(self):
        self.engine = PersonaEngine()
        self.parser = ChatParser()
        self.chunker = ChatChunker()

    async def stream_extract(
        self,
        raw_text: str,
        my_username: str,
        slug: str,
    ) -> AsyncGenerator[dict, None]:
        """异步生成器：逐天分析，yield SSE 事件。"""

        # 1) 解析
        fmt = self.parser.detect_format(raw_text)
        messages, stats = self.parser.parse(raw_text, fmt, my_username)

        if not messages:
            yield {"event": "error", "data": {"message": "未能解析出任何消息"}}
            return

        target_name = stats.get("target_name", "对方")

        # 2) 按天严格分块
        daily_chunks = self.chunker.chunk_by_day(messages)
        total_days = len(daily_chunks)

        yield {
            "event": "started",
            "data": {
                "total_days": total_days,
                "total_messages": stats["total_messages"],
                "target_name": target_name,
                "target_aliases": stats.get("target_aliases", []),
            },
        }

        # 3) 逐天 Track A 分析
        profile = PersonaProfile(nickname=target_name)
        snapshots: list[DailySnapshot] = []
        e3_accum = {"empathy": [], "stability": [], "boundary": []}

        for i, chunk in enumerate(daily_chunks):
            day_str = chunk.date_start.isoformat()

            if chunk.total_count < 2:
                snap = DailySnapshot(
                    day=day_str,
                    day_summary="消息过少，跳过分析",
                    message_count=chunk.total_count,
                    target_msg_count=len(chunk.target_messages),
                )
                snapshots.append(snap)
                yield {
                    "event": "day_skipped",
                    "data": {"day": day_str, "reason": "消息过少", "progress": i + 1, "total": total_days},
                }
                continue

            raw = chunk.raw_text
            if len(raw) > 60000:
                raw = raw[:60000] + "\n...(截断)"

            try:
                chunk_profile = self.engine._track_a_dialogue_analysis(
                    raw, target_name, my_username
                )

                # 提取 e3_estimate 和 day_summary (LLM 返回的额外字段)
                e3_est = getattr(chunk_profile, 'e3_baseline', None) or {}
                day_summary = ""

                # 由于 PersonaProfile 过滤了未知字段，需要重新解析原始响应
                # 在 _track_a 里已经过滤了, 这里用 chunk_profile 的已有字段
                new_tags = chunk_profile.personality_tags

                profile = PersonaEngine._merge_profiles(profile, chunk_profile)

            except Exception as exc:
                snap = DailySnapshot(
                    day=day_str,
                    day_summary=f"分析失败: {str(exc)[:50]}",
                    message_count=chunk.total_count,
                    target_msg_count=len(chunk.target_messages),
                )
                snapshots.append(snap)
                yield {
                    "event": "day_error",
                    "data": {"day": day_str, "error": str(exc)[:100], "progress": i + 1, "total": total_days},
                }
                continue

            # 累积 E3
            for dim in ("empathy", "stability", "boundary"):
                if e3_est.get(dim) is not None:
                    e3_accum[dim].append(float(e3_est[dim]))

            cumulative_e3 = {
                dim: round(sum(vals) / len(vals), 3) if vals else 0.5
                for dim, vals in e3_accum.items()
            }

            snap = DailySnapshot(
                day=day_str,
                day_summary=day_summary or f"分析了 {chunk.total_count} 条对话",
                new_tags=new_tags,
                e3_estimate=e3_est if e3_est else None,
                cumulative_tags=profile.personality_tags[:],
                cumulative_e3=cumulative_e3,
                message_count=chunk.total_count,
                target_msg_count=len(chunk.target_messages),
            )
            snapshots.append(snap)

            # 实时保存当前 profile（允许分析过程中就聊天）
            profile.e3_baseline = cumulative_e3
            profile.daily_snapshots = [s.to_dict() for s in snapshots]
            if not profile.core_identity:
                profile.core_identity = f"{target_name} 的数字人格（构建中...）"
            if not profile.boundary_rules:
                profile.boundary_rules = ["不模拟复合场景", "不鼓励纠缠行为"]
            self.engine.save_profile(profile, slug)

            yield {
                "event": "day_done",
                "data": {
                    "day": day_str,
                    "snapshot": snap.to_dict(),
                    "progress": i + 1,
                    "total": total_days,
                    "cumulative_e3": cumulative_e3,
                    "cumulative_tags": profile.personality_tags[:10],
                },
            }

        # 4) Track B: 语言统计
        yield {"event": "tone_start", "data": {"message": "正在分析语言风格..."}}

        all_target_contents = [
            m.content for m in messages if m.is_target
        ]
        tone_style = self.engine._track_b_language_stats(all_target_contents)
        profile.tone_style = tone_style

        # 5) 最终整理
        if not profile.core_identity or profile.core_identity.endswith("构建中...)"):
            profile.core_identity = f"{target_name} 的数字人格"

        final_e3 = {
            dim: round(sum(vals) / len(vals), 3) if vals else 0.5
            for dim, vals in e3_accum.items()
        }
        profile.e3_baseline = final_e3
        profile.daily_snapshots = [s.to_dict() for s in snapshots]

        self.engine.save_profile(profile, slug)

        # 保存日快照到单独目录
        snap_dir = PERSONA_DIR / f"{slug}_daily"
        snap_dir.mkdir(parents=True, exist_ok=True)
        for snap in snapshots:
            path = snap_dir / f"{snap.day}.json"
            path.write_text(
                json.dumps(snap.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        yield {
            "event": "complete",
            "data": {
                "slug": slug,
                "profile": profile.to_dict(),
                "total_days_analyzed": len([s for s in snapshots if s.e3_estimate]),
                "final_e3": final_e3,
            },
        }

    async def stream_extract_with_raw_response(
        self,
        raw_text: str,
        my_username: str,
        slug: str,
    ) -> AsyncGenerator[dict, None]:
        """增强版: Track A 也返回 e3_estimate 和 day_summary。
        通过直接调用 LLM 而非 engine._track_a 来获取完整 JSON。
        """
        fmt = self.parser.detect_format(raw_text)
        messages, stats = self.parser.parse(raw_text, fmt, my_username)

        if not messages:
            yield {"event": "error", "data": {"message": "未能解析出任何消息"}}
            return

        target_name = stats.get("target_name", "对方")
        daily_chunks = self.chunker.chunk_by_day(messages)
        total_days = len(daily_chunks)

        yield {
            "event": "started",
            "data": {
                "total_days": total_days,
                "total_messages": stats["total_messages"],
                "target_name": target_name,
                "target_aliases": stats.get("target_aliases", []),
            },
        }

        profile = PersonaProfile(nickname=target_name)
        snapshots: list[DailySnapshot] = []
        e3_accum = {"empathy": [], "stability": [], "boundary": []}

        from src.persona.engine import _DIALOGUE_ANALYSIS_PROMPT, JUDGE_MODEL

        for i, chunk in enumerate(daily_chunks):
            day_str = chunk.date_start.isoformat()

            if chunk.total_count < 2:
                snap = DailySnapshot(
                    day=day_str,
                    day_summary="消息过少，跳过",
                    message_count=chunk.total_count,
                    target_msg_count=len(chunk.target_messages),
                )
                snapshots.append(snap)
                yield {
                    "event": "day_skipped",
                    "data": {"day": day_str, "progress": i + 1, "total": total_days},
                }
                continue

            raw = chunk.raw_text
            if len(raw) > 60000:
                raw = raw[:60000] + "\n...(截断)"

            try:
                prompt = _DIALOGUE_ANALYSIS_PROMPT.format(
                    target_name=target_name,
                    my_name=my_username,
                    dialogue=raw,
                )
                resp = self.engine.client.chat.completions.create(
                    model=JUDGE_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                data = json.loads(resp.choices[0].message.content)

                # 提取完整数据（包括 e3_estimate 和 day_summary）
                e3_est = data.pop("e3_estimate", {}) or {}
                day_summary = data.pop("day_summary", "") or ""

                chunk_profile = PersonaProfile(**{
                    k: v for k, v in data.items()
                    if k in PersonaProfile.__dataclass_fields__
                })
                new_tags = chunk_profile.personality_tags[:]
                profile = PersonaEngine._merge_profiles(profile, chunk_profile)

            except Exception as exc:
                snap = DailySnapshot(
                    day=day_str,
                    day_summary=f"分析失败: {str(exc)[:50]}",
                    message_count=chunk.total_count,
                    target_msg_count=len(chunk.target_messages),
                )
                snapshots.append(snap)
                yield {
                    "event": "day_error",
                    "data": {"day": day_str, "error": str(exc)[:100], "progress": i + 1, "total": total_days},
                }
                continue

            for dim in ("empathy", "stability", "boundary"):
                val = e3_est.get(dim)
                if val is not None:
                    try:
                        e3_accum[dim].append(float(val))
                    except (ValueError, TypeError):
                        pass

            cumulative_e3 = {
                dim: round(sum(vals) / len(vals), 3) if vals else 0.5
                for dim, vals in e3_accum.items()
            }

            snap = DailySnapshot(
                day=day_str,
                day_summary=day_summary,
                new_tags=new_tags,
                e3_estimate=e3_est,
                cumulative_tags=profile.personality_tags[:],
                cumulative_e3=cumulative_e3,
                message_count=chunk.total_count,
                target_msg_count=len(chunk.target_messages),
            )
            snapshots.append(snap)

            profile.e3_baseline = cumulative_e3
            profile.daily_snapshots = [s.to_dict() for s in snapshots]
            if not profile.core_identity:
                profile.core_identity = f"{target_name} 的数字人格（构建中...）"
            if not profile.boundary_rules:
                profile.boundary_rules = ["不模拟复合场景", "不鼓励纠缠行为"]
            self.engine.save_profile(profile, slug)

            yield {
                "event": "day_done",
                "data": {
                    "day": day_str,
                    "snapshot": snap.to_dict(),
                    "progress": i + 1,
                    "total": total_days,
                    "cumulative_e3": cumulative_e3,
                    "cumulative_tags": profile.personality_tags[:10],
                },
            }

        # Track B
        yield {"event": "tone_start", "data": {"message": "正在分析语言风格..."}}
        all_target = [m.content for m in messages if m.is_target]
        tone = self.engine._track_b_language_stats(all_target)
        profile.tone_style = tone

        if not profile.core_identity or "构建中" in profile.core_identity:
            profile.core_identity = f"{target_name} 的数字人格"

        final_e3 = {
            dim: round(sum(vals) / len(vals), 3) if vals else 0.5
            for dim, vals in e3_accum.items()
        }
        profile.e3_baseline = final_e3
        profile.daily_snapshots = [s.to_dict() for s in snapshots]
        self.engine.save_profile(profile, slug)

        snap_dir = PERSONA_DIR / f"{slug}_daily"
        snap_dir.mkdir(parents=True, exist_ok=True)
        for snap in snapshots:
            path = snap_dir / f"{snap.day}.json"
            path.write_text(
                json.dumps(snap.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        yield {
            "event": "complete",
            "data": {
                "slug": slug,
                "profile": profile.to_dict(),
                "total_days_analyzed": len([s for s in snapshots if s.e3_estimate]),
                "final_e3": final_e3,
            },
        }
