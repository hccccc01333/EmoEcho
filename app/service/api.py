"""FastAPI 后端: chat / persona / memory / insights 四组接口。"""
from __future__ import annotations

import hashlib
import json
import time as _time
import uuid as _uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agent.orchestrator import AgentOrchestrator
from src.persona.engine import PersonaEngine
from src.persona.chat_parser import ChatParser
from src.persona.chat_chunker import ChatChunker
from src.persona.stream_extractor import StreamExtractor
from src.memory.engine import MemoryEngine
from src.config import PERSONA_DIR, DATA_DIR

app = FastAPI(title="EmoEcho API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_orchestrator: AgentOrchestrator | None = None
_persona_engine = PersonaEngine()
_chat_parser = ChatParser()
_chat_chunker = ChatChunker()
_stream_extractor = StreamExtractor()


def _get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


# ── Chat ──

class ChatRequest(BaseModel):
    message: str
    persona_slug: str | None = None


class ChatResponse(BaseModel):
    reply: str
    e3_score: dict
    eaf: dict
    policy: str
    strategy: str
    skill_used: str | None
    safety_level: str
    memories_used: int
    latency_ms: float
    msg_id: str


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    orch = _get_orchestrator()
    if req.persona_slug:
        try:
            orch.load_persona(req.persona_slug)
        except FileNotFoundError:
            raise HTTPException(404, f"人格档案 '{req.persona_slug}' 不存在")
    result = orch.chat(req.message)
    return ChatResponse(**result.to_dict())


@app.post("/chat/new-session")
def new_session():
    orch = _get_orchestrator()
    orch.new_session()
    return {"status": "ok"}


# ── Chat History ──

_CONV_DIR = DATA_DIR / "conversations"
_CONV_DIR.mkdir(parents=True, exist_ok=True)


class SaveConversationRequest(BaseModel):
    title: str = ""
    messages: list[dict]
    persona_slug: str | None = None


@app.post("/chat/history")
def save_conversation(req: SaveConversationRequest):
    conv_id = _uuid.uuid4().hex[:12]
    title = req.title or (req.messages[0]["content"][:30] if req.messages else "新对话")
    data = {
        "id": conv_id,
        "title": title,
        "messages": req.messages,
        "persona_slug": req.persona_slug,
        "created_at": _time.time(),
        "updated_at": _time.time(),
        "archived": False,
    }
    path = _CONV_DIR / f"{conv_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": conv_id, "title": title}


@app.get("/chat/history")
def list_conversations(archived: bool = False):
    convs = []
    for p in sorted(_CONV_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("archived", False) != archived:
                continue
            convs.append({
                "id": data["id"],
                "title": data["title"],
                "message_count": len(data.get("messages", [])),
                "persona_slug": data.get("persona_slug"),
                "updated_at": data.get("updated_at", 0),
            })
        except Exception:
            continue
    return {"conversations": convs}


@app.get("/chat/history/{conv_id}")
def load_conversation(conv_id: str):
    path = _CONV_DIR / f"{conv_id}.json"
    if not path.exists():
        raise HTTPException(404, "对话记录不存在")
    return json.loads(path.read_text(encoding="utf-8"))


@app.put("/chat/history/{conv_id}")
def update_conversation(conv_id: str, req: SaveConversationRequest):
    path = _CONV_DIR / f"{conv_id}.json"
    if not path.exists():
        raise HTTPException(404, "对话记录不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["messages"] = req.messages
    if req.title:
        data["title"] = req.title
    data["updated_at"] = _time.time()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok"}


@app.delete("/chat/history/{conv_id}")
def delete_conversation(conv_id: str):
    path = _CONV_DIR / f"{conv_id}.json"
    if path.exists():
        path.unlink()
    return {"status": "deleted"}


@app.patch("/chat/history/{conv_id}/archive")
def archive_conversation(conv_id: str):
    path = _CONV_DIR / f"{conv_id}.json"
    if not path.exists():
        raise HTTPException(404, "对话记录不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["archived"] = not data.get("archived", False)
    data["updated_at"] = _time.time()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "archived": data["archived"]}


# ── Persona ──

_SUPPORTED_EXT = {".txt", ".csv", ".json", ".md", ".log"}

# 缓存：preview 解析结果暂存，upload 时复用
_preview_cache: dict[str, dict] = {}


def _extract_text_from_file(filename: str, raw: bytes) -> str:
    """从上传文件中提取纯文本。"""
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        import zipfile, io, xml.etree.ElementTree as ET
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml_content = zf.read("word/document.xml")
        tree = ET.fromstring(xml_content)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return "\n".join(
            "".join(node.text or "" for node in p.iter(f"{{{ns['w']}}}t"))
            for p in tree.iter(f"{{{ns['w']}}}p")
        )
    for enc in ("utf-8", "gbk", "gb2312", "utf-16"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")



@app.post("/persona/detect-speakers")
async def detect_speakers(
    files: list[UploadFile] = File(...),
):
    """上传文件 -> 格式检测 -> 返回发言者列表（不需要用户名）。"""
    all_text_parts: list[str] = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in _SUPPORTED_EXT and ext != ".docx":
            raise HTTPException(400, f"不支持的文件格式: {ext}")
        content = await f.read()
        all_text_parts.append(_extract_text_from_file(f.filename or "file.txt", content))

    raw_text = "\n\n".join(all_text_parts)
    if len(raw_text.strip()) < 20:
        raise HTTPException(400, "文件内容过短")

    fmt = _chat_parser.detect_format(raw_text)
    speakers = fmt.detected_speakers

    if not speakers:
        messages, stats = _chat_parser.parse(raw_text, fmt, "__placeholder__")
        speakers = stats.get("speakers", [])

    cache_key = hashlib.md5(raw_text[:2000].encode()).hexdigest()
    _preview_cache[cache_key] = {"raw_text": raw_text}

    return {
        "cache_key": cache_key,
        "format_source": fmt.source,
        "speakers": speakers,
    }


@app.post("/persona/preview")
async def preview_chat(
    my_username: str = Form(...),
    files: list[UploadFile] = File(None),
    cache_key: str = Form(None),
):
    """预检：解析 -> 返回 speakers + 分块预览。支持 cache_key 复用。"""
    if cache_key and cache_key in _preview_cache:
        raw_text = _preview_cache[cache_key]["raw_text"]
    elif files:
        all_text_parts: list[str] = []
        for f in files:
            ext = Path(f.filename or "").suffix.lower()
            if ext not in _SUPPORTED_EXT and ext != ".docx":
                raise HTTPException(400, f"不支持的文件格式: {ext}")
            content = await f.read()
            all_text_parts.append(_extract_text_from_file(f.filename or "file.txt", content))
        raw_text = "\n\n".join(all_text_parts)
    else:
        raise HTTPException(400, "请上传文件或提供 cache_key")

    if len(raw_text.strip()) < 20:
        raise HTTPException(400, "文件内容过短")

    fmt = _chat_parser.detect_format(raw_text)
    messages, stats = _chat_parser.parse(raw_text, fmt, my_username)

    if not messages:
        raise HTTPException(400, "未能解析出任何消息，请检查文件格式")

    preview = _chat_chunker.get_preview(messages)

    new_key = hashlib.md5(raw_text[:2000].encode()).hexdigest()
    _preview_cache[new_key] = {
        "raw_text": raw_text,
        "my_username": my_username,
    }

    return {
        "cache_key": new_key,
        "format_source": fmt.source,
        "stats": stats,
        "preview": preview,
    }


@app.post("/persona/upload")
async def upload_persona(
    slug: str = Form(...),
    my_username: str = Form(...),
    files: list[UploadFile] = File(None),
    cache_key: str = Form(None),
):
    """上传文件生成人格档案（双轨分析）。可复用 preview 的 cache_key。"""
    if cache_key and cache_key in _preview_cache:
        cached = _preview_cache.pop(cache_key)
        raw_text = cached["raw_text"]
        my_username = cached.get("my_username", my_username)
    elif files:
        all_text_parts: list[str] = []
        for f in files:
            ext = Path(f.filename or "").suffix.lower()
            if ext not in _SUPPORTED_EXT and ext != ".docx":
                raise HTTPException(400, f"不支持的文件格式: {ext}")
            content = await f.read()
            all_text_parts.append(_extract_text_from_file(f.filename or "file.txt", content))
        raw_text = "\n\n".join(all_text_parts)
    else:
        raise HTTPException(400, "请上传文件或提供 cache_key")

    if len(raw_text.strip()) < 20:
        raise HTTPException(400, "文件内容过短，无法提取人格特征")

    fmt = _chat_parser.detect_format(raw_text)
    messages, stats = _chat_parser.parse(raw_text, fmt, my_username)

    if not messages or stats["target_count"] < 3:
        profile = _persona_engine.extract_from_text(raw_text)
    else:
        chunks = _chat_chunker.chunk(messages)
        target_name = stats["target_name"] or "对方"
        profile = _persona_engine.extract_from_chat_logs(
            chunks, target_name, my_username
        )

    path = _persona_engine.save_profile(profile, slug)
    return {
        "slug": slug,
        "path": str(path),
        "profile": profile.to_dict(),
        "stats": stats,
    }


class PersonaCreateRequest(BaseModel):
    slug: str
    material: str


@app.post("/persona/create")
def create_persona(req: PersonaCreateRequest):
    profile = _persona_engine.extract_from_text(req.material)
    path = _persona_engine.save_profile(profile, req.slug)
    return {"slug": req.slug, "path": str(path), "profile": profile.to_dict()}


@app.get("/persona/{slug}")
def get_persona(slug: str):
    try:
        profile = _persona_engine.load_profile(slug)
        return profile.to_dict()
    except FileNotFoundError:
        raise HTTPException(404, f"人格档案 '{slug}' 不存在")


@app.get("/persona/list/all")
def list_personas():
    slugs = [p.stem for p in PERSONA_DIR.glob("*.json")]
    return {"personas": slugs}


@app.delete("/persona/{slug}")
def delete_persona(slug: str):
    path = PERSONA_DIR / f"{slug}.json"
    if not path.exists():
        raise HTTPException(404, f"人格档案 '{slug}' 不存在")
    path.unlink()
    return {"status": "deleted", "slug": slug}


@app.post("/persona/stream-extract")
async def stream_extract_persona(
    slug: str = Form(...),
    my_username: str = Form(...),
    files: list[UploadFile] = File(None),
    cache_key: str = Form(None),
):
    """SSE 流式人格提取：逐天分析，实时推送进度。"""
    if cache_key and cache_key in _preview_cache:
        raw_text = _preview_cache[cache_key].get("raw_text", "")
        my_username = _preview_cache[cache_key].get("my_username", my_username)
    elif files:
        parts: list[str] = []
        for f in files:
            content = await f.read()
            parts.append(_extract_text_from_file(f.filename or "file.txt", content))
        raw_text = "\n\n".join(parts)
    else:
        raise HTTPException(400, "请上传文件或提供 cache_key")

    if len(raw_text.strip()) < 20:
        raise HTTPException(400, "文件内容过短")

    async def _sse_generator():
        async for event in _stream_extractor.stream_extract_with_raw_response(
            raw_text, my_username, slug
        ):
            evt_type = event.get("event", "message")
            evt_data = json.dumps(event.get("data", {}), ensure_ascii=False)
            yield f"event: {evt_type}\ndata: {evt_data}\n\n"

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/persona/{slug}/daily-snapshots")
def get_daily_snapshots(slug: str):
    """获取人格档案的逐日快照。"""
    try:
        profile = _persona_engine.load_profile(slug)
        return {"snapshots": profile.daily_snapshots, "e3_baseline": profile.e3_baseline}
    except FileNotFoundError:
        raise HTTPException(404, f"人格档案 '{slug}' 不存在")


# ── Insights Baseline ──

@app.get("/insights/baseline/{slug}")
def insights_baseline(slug: str):
    """返回人格基线分数（从人格档案的 e3_baseline 和 daily_snapshots）。"""
    try:
        profile = _persona_engine.load_profile(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"人格档案 '{slug}' 不存在")

    e3 = profile.e3_baseline or {"empathy": 0.5, "stability": 0.5, "boundary": 0.5}

    trust = max(1.0 - e3.get("boundary", 0.5) * 1.5, 0.0)
    intimacy = min(e3.get("empathy", 0.5) * 1.4, 1.0)
    stability_val = e3.get("stability", 0.5)

    return {
        "e3_baseline": e3,
        "radar_baseline": [
            {"name": "信任度", "value": round(trust, 3)},
            {"name": "亲密度", "value": round(intimacy, 3)},
            {"name": "冲突频率", "value": round(1.0 - stability_val, 3)},
            {"name": "依赖程度", "value": round(0.5, 3)},
            {"name": "成长性", "value": round(0.3, 3)},
            {"name": "边界健康度", "value": round(stability_val, 3)},
        ],
        "daily_snapshots": profile.daily_snapshots,
    }


# ── Memory ──

@app.get("/memory/search")
def search_memory(q: str, limit: int = 10):
    orch = _get_orchestrator()
    results = orch.memory.hybrid_search(q, limit=limit)
    return {"results": results}


@app.get("/memory/corrections")
def get_corrections():
    orch = _get_orchestrator()
    return {"corrections": orch.memory.get_active_corrections()}


@app.post("/memory/forget")
def forget_all():
    orch = _get_orchestrator()
    orch.memory.forget_all()
    return {"status": "all data deleted"}


# ── Insights ──

@app.get("/insights/emotion-timeline")
def emotion_timeline(limit: int = 100):
    orch = _get_orchestrator()
    return {"data": orch.memory.get_emotion_timeline(limit)}


@app.get("/insights/e3-history")
def e3_history(limit: int = 100):
    orch = _get_orchestrator()
    return {"data": orch.memory.get_e3_history(limit)}


@app.get("/insights/session-summary")
def session_summary():
    orch = _get_orchestrator()
    return orch.memory.get_session_summary()


@app.get("/insights/heatmap")
def heatmap():
    orch = _get_orchestrator()
    return {"data": orch.memory.get_heatmap_data()}


@app.get("/insights/relationship-radar")
def relationship_radar():
    """关系维度雷达图: 从 turn_metrics 聚合计算 6 维度。"""
    orch = _get_orchestrator()
    summary = orch.memory.get_session_summary()
    total = max(summary["total_turns"], 1)

    trust = max(1.0 - summary["avg_boundary"] * 2, 0.0)
    intimacy = min(summary["avg_empathy"] * 1.5, 1.0)
    conflict = 1.0 - summary["avg_stability"]
    dependency = summary.get("avg_intensity", 0.0)
    growth = min(
        (summary["policy_distribution"].get("guide_change", 0) / total) * 5, 1.0
    )
    boundary_health = summary["avg_stability"]

    return {
        "dimensions": [
            {"name": "信任度", "value": round(trust, 3)},
            {"name": "亲密度", "value": round(intimacy, 3)},
            {"name": "冲突频率", "value": round(conflict, 3)},
            {"name": "依赖程度", "value": round(dependency, 3)},
            {"name": "成长性", "value": round(growth, 3)},
            {"name": "边界健康度", "value": round(boundary_health, 3)},
        ]
    }


@app.get("/insights/personality-drift")
def personality_drift():
    """性格漂移: 追踪 E3 各维度随时间的变化。"""
    orch = _get_orchestrator()
    history = orch.memory.get_e3_history(limit=200)
    if len(history) < 2:
        return {"data": [], "corrections": []}

    window = 10
    smoothed = []
    for i in range(0, len(history), window):
        chunk = history[i:i + window]
        if not chunk:
            break
        smoothed.append({
            "timestamp": chunk[-1]["timestamp"],
            "empathy": round(sum(c["e3_empathy"] for c in chunk) / len(chunk), 3),
            "stability": round(sum(c["e3_stability"] for c in chunk) / len(chunk), 3),
            "boundary": round(sum(c["e3_boundary"] for c in chunk) / len(chunk), 3),
        })

    corrections = orch.memory.get_active_corrections()
    correction_events = [
        {"timestamp": c["created_at"], "text": c["correction"][:60]}
        for c in corrections[:10]
    ]

    return {"data": smoothed, "corrections": correction_events}


# ── Health ──

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


# ── Static Files (production: serve frontend dist) ──

_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST_DIR.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = _DIST_DIR / full_path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(_DIST_DIR / "index.html")

    app.mount("/assets", StaticFiles(directory=str(_DIST_DIR / "assets")), name="assets")
