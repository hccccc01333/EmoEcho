"""MemoryEngine: 双层记忆系统（事实记忆 + 情绪记忆）+ 混合检索。

存储: SQLite（全文检索 FTS5 + 结构化字段）
检索: 关键词 FTS + 向量相似度 -> 混合重排
"""
import sqlite3
import json
import time
from dataclasses import dataclass
from pathlib import Path

from src.config import DB_PATH


@dataclass
class MemoryRecord:
    """一条记忆记录。"""
    id: int | None = None
    layer: str = "fact"          # "fact" | "emotion" | "correction"
    content: str = ""
    tags: str = ""               # 逗号分隔标签
    emotion_valence: float = 0.0  # -1(极负) ~ 1(极正)
    importance: float = 0.5      # 0~1
    source: str = "chat"         # chat | import | correction
    created_at: float = 0.0
    embedding: bytes = b""       # 预留向量字段


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layer TEXT NOT NULL DEFAULT 'fact',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    emotion_valence REAL DEFAULT 0.0,
    importance REAL DEFAULT 0.5,
    source TEXT DEFAULT 'chat',
    created_at REAL NOT NULL,
    embedding BLOB DEFAULT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
USING fts5(content, tags, content='memories', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES('delete', old.id, old.content, old.tags);
END;

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_text TEXT NOT NULL,
    correction TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    created_at REAL NOT NULL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT,
    feedback_type TEXT NOT NULL,
    content TEXT DEFAULT '',
    score REAL DEFAULT 0.0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS adaptive_profile (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS turn_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT,
    timestamp REAL NOT NULL,
    e3_empathy REAL DEFAULT 0.0,
    e3_stability REAL DEFAULT 1.0,
    e3_boundary REAL DEFAULT 0.0,
    policy TEXT DEFAULT 'default',
    strategy TEXT DEFAULT 'natural_companion',
    emotion_stage TEXT DEFAULT 'pre_trigger',
    emotion_intensity REAL DEFAULT 0.0,
    emotion_sadness REAL DEFAULT 0.0,
    emotion_anger REAL DEFAULT 0.0,
    emotion_anxiety REAL DEFAULT 0.0,
    emotion_loneliness REAL DEFAULT 0.0,
    emotion_warmth REAL DEFAULT 0.0,
    distortion_type TEXT DEFAULT 'none',
    distortion_score REAL DEFAULT 0.0,
    attachment_activation REAL DEFAULT 0.0,
    distance_suggestion TEXT DEFAULT 'neutral',
    skill_used TEXT,
    safety_level TEXT DEFAULT 'safe',
    latency_ms REAL DEFAULT 0.0
);
"""


class MemoryEngine:
    """双层记忆引擎。"""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = str(db_path or DB_PATH)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._conn()
        conn.executescript(_SCHEMA_SQL)
        conn.close()

    # ── 写入 ──

    def add_memory(self, content: str, layer: str = "fact",
                   tags: str = "", emotion_valence: float = 0.0,
                   importance: float = 0.5, source: str = "chat") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO memories (layer, content, tags, emotion_valence, importance, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (layer, content, tags, emotion_valence, importance, source, time.time()),
        )
        conn.commit()
        mid = cur.lastrowid
        conn.close()
        return mid

    def add_correction(self, trigger_text: str, correction: str, priority: int = 5) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO corrections (trigger_text, correction, priority, created_at) VALUES (?, ?, ?, ?)",
            (trigger_text, correction, priority, time.time()),
        )
        conn.commit()
        cid = cur.lastrowid
        conn.close()
        return cid

    def add_feedback(self, feedback_type: str, content: str = "",
                     score: float = 0.0, msg_id: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO feedback_events (msg_id, feedback_type, content, score, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg_id, feedback_type, content, score, time.time()),
        )
        conn.commit()
        fid = cur.lastrowid
        conn.close()
        return fid

    # ── 检索 ──

    def search_keyword(self, query: str, limit: int = 10) -> list[dict]:
        """FTS5 关键词检索。"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT m.*, rank FROM memories_fts f "
            "JOIN memories m ON f.rowid = m.id "
            "WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_recent(self, limit: int = 20) -> list[dict]:
        """最近 N 条记忆（短期窗口）。"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_by_layer(self, layer: str, limit: int = 20) -> list[dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM memories WHERE layer = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
            (layer, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_active_corrections(self) -> list[dict]:
        """获取所有生效的纠正记忆（高优先级优先）。"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM corrections WHERE active = 1 ORDER BY priority DESC, created_at DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def hybrid_search(self, query: str, limit: int = 10) -> list[dict]:
        """混合检索: FTS + 最近记忆 + 纠正记忆，去重后按重要性排序。"""
        fts_results = self.search_keyword(query, limit=limit)
        recent = self.search_recent(limit=5)
        seen_ids = set()
        merged = []
        for r in fts_results + recent:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                merged.append(r)
        merged.sort(key=lambda x: (x.get("importance", 0), x.get("created_at", 0)), reverse=True)
        return merged[:limit]

    # ── 自适应配置 ──

    def get_adaptive(self, key: str, default: str = "") -> str:
        conn = self._conn()
        row = conn.execute("SELECT value FROM adaptive_profile WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else default

    def set_adaptive(self, key: str, value: str):
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO adaptive_profile (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        conn.commit()
        conn.close()

    # ── 对话指标 ──

    def record_turn_metrics(self, metrics: dict):
        """每轮对话写入 turn_metrics 表。"""
        conn = self._conn()
        conn.execute(
            "INSERT INTO turn_metrics "
            "(msg_id, timestamp, e3_empathy, e3_stability, e3_boundary, "
            "policy, strategy, emotion_stage, emotion_intensity, "
            "emotion_sadness, emotion_anger, emotion_anxiety, emotion_loneliness, emotion_warmth, "
            "distortion_type, distortion_score, attachment_activation, distance_suggestion, "
            "skill_used, safety_level, latency_ms) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                metrics.get("msg_id", ""),
                metrics.get("timestamp", time.time()),
                metrics.get("e3_empathy", 0.0),
                metrics.get("e3_stability", 1.0),
                metrics.get("e3_boundary", 0.0),
                metrics.get("policy", "default"),
                metrics.get("strategy", "natural_companion"),
                metrics.get("emotion_stage", "pre_trigger"),
                metrics.get("emotion_intensity", 0.0),
                metrics.get("emotion_sadness", 0.0),
                metrics.get("emotion_anger", 0.0),
                metrics.get("emotion_anxiety", 0.0),
                metrics.get("emotion_loneliness", 0.0),
                metrics.get("emotion_warmth", 0.0),
                metrics.get("distortion_type", "none"),
                metrics.get("distortion_score", 0.0),
                metrics.get("attachment_activation", 0.0),
                metrics.get("distance_suggestion", "neutral"),
                metrics.get("skill_used"),
                metrics.get("safety_level", "safe"),
                metrics.get("latency_ms", 0.0),
            ),
        )
        conn.commit()
        conn.close()

    def get_emotion_timeline(self, limit: int = 100) -> list[dict]:
        """情绪时间河流图数据。"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT timestamp, emotion_sadness, emotion_anger, emotion_anxiety, "
            "emotion_loneliness, emotion_warmth, emotion_intensity "
            "FROM turn_metrics ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]

    def get_e3_history(self, limit: int = 100) -> list[dict]:
        """E3-Score 历史趋势数据。"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT timestamp, e3_empathy, e3_stability, e3_boundary, policy, strategy "
            "FROM turn_metrics ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]

    def get_session_summary(self) -> dict:
        """会话摘要统计。"""
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as total_turns, "
            "AVG(e3_empathy) as avg_empathy, AVG(e3_stability) as avg_stability, "
            "AVG(e3_boundary) as avg_boundary, AVG(latency_ms) as avg_latency, "
            "AVG(emotion_intensity) as avg_intensity "
            "FROM turn_metrics"
        ).fetchone()
        policy_rows = conn.execute(
            "SELECT policy, COUNT(*) as cnt FROM turn_metrics GROUP BY policy ORDER BY cnt DESC"
        ).fetchall()
        conn.close()
        return {
            "total_turns": row["total_turns"] or 0,
            "avg_empathy": round(row["avg_empathy"] or 0, 3),
            "avg_stability": round(row["avg_stability"] or 0, 3),
            "avg_boundary": round(row["avg_boundary"] or 0, 3),
            "avg_latency_ms": round(row["avg_latency"] or 0, 1),
            "avg_intensity": round(row["avg_intensity"] or 0, 3),
            "policy_distribution": {r["policy"]: r["cnt"] for r in policy_rows},
        }

    def get_heatmap_data(self) -> list[dict]:
        """对话热力图数据（按小时和星期聚合）。"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT timestamp, emotion_intensity FROM turn_metrics"
        ).fetchall()
        conn.close()
        from datetime import datetime
        buckets: dict[tuple[int, int], list[float]] = {}
        for r in rows:
            dt = datetime.fromtimestamp(r["timestamp"])
            key = (dt.weekday(), dt.hour)
            buckets.setdefault(key, []).append(r["emotion_intensity"])
        return [
            {"weekday": k[0], "hour": k[1], "count": len(v), "avg_intensity": round(sum(v)/len(v), 3)}
            for k, v in sorted(buckets.items())
        ]

    # ── 遗忘 ──

    def forget_all(self):
        """一键删除所有数据（可遗忘设计）。"""
        conn = self._conn()
        conn.executescript("""
            DELETE FROM memories;
            DELETE FROM memories_fts;
            DELETE FROM corrections;
            DELETE FROM feedback_events;
            DELETE FROM adaptive_profile;
            DELETE FROM turn_metrics;
        """)
        conn.close()
