"""全局配置：路径常量、模型参数、策略阈值。"""
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# ── 路径 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PERSONA_DIR = DATA_DIR / "personas"
RAW_DIR = DATA_DIR / "raw"
VECTOR_DIR = DATA_DIR / "vector_store"
DB_PATH = DATA_DIR / "memory.db"

PERSONA_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DIR.mkdir(parents=True, exist_ok=True)

# ── LLM ──
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-flash")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "deepseek-v4-pro")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LOCAL_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "qwen2.5:7b")

# ── E3-Score 阈值 ──
E3_BOUNDARY_THRESHOLD = 0.65
E3_EMPATHY_HIGH = 0.70
E3_STABILITY_LOW = 0.45

# ── 自学习 ──
EMA_ALPHA = 0.1          # 偏好更新指数移动平均系数
CORRECTION_PRIORITY = 5   # 纠正记忆默认优先级（1-10）
PROFILE_SYNC_INTERVAL = 50  # 每 N 轮做一次人格同步
