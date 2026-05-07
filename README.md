# 99 - 心迹回声桌宠Agent（EmoEcho Pet Agent）

> **项目类型**：秋招主打项目 / 桌面端 AI Agent / 数字人格  
> **技术栈**：Tauri + React + TypeScript + Python(FastAPI) + SQLite + 向量检索 + LLM API/Ollama  
> **项目定位**：做一个比 `ex-skill` 更完整的桌面数字人格系统（人格复刻 + 情感算法 + 技能执行 + 自学习）

---

## 一、项目简介

`心迹回声桌宠Agent` 是一个本地优先的桌面陪伴系统。用户可投喂聊天记录、文档和事件素材，自动生成数字人格，并以桌面宠物形态持续陪伴和互动。

核心链路：

```text
原始资料投喂 -> 人格抽取(PersonaEngine)
    -> 记忆建库(MemoryEngine)
    -> 情感策略路由(EmotionEngine / E3-Score)
    -> 安全预检(SafetyGuard)
    -> 技能调用/LLM生成(SkillHub / Orchestrator)
    -> 自学习反馈(SelfLearner)
    -> 桌宠交互输出
```

---

## 二、相对前任skill的五大增强

1. **桌面宠物化体验** - 常驻桌面 + 悬浮球 + 情绪状态动画，不只是命令行
2. **心理学增强算法** - E3-Score（Empathy/Stability/Boundary），融合依恋理论、NVC、CBT、MI 四套理论
3. **三层自学习** - 会话级偏好/纠正记忆/周期性人格微调，越聊越像
4. **Skill技能系统** - 统一协议热插拔：情绪安抚、关系复盘、学习监督
5. **安全边界硬控** - 四级风险响应 + 危机热线 + 一键遗忘

---

## 三、系统架构

```text
AgentOrchestrator (决策主循环)
├── Step1: SafetyGuard      -- 安全预检（四级风险）
├── Step2: EmotionEngine     -- E3-Score 计算 + 策略路由
├── Step3: MemoryEngine      -- 双层记忆混合检索
├── Step4: SkillHub          -- 意图匹配 -> Skill / 默认对话
├── Step5: LLM Generate      -- 人格Prompt + 记忆 + 策略 -> 回复
└── Step6: SelfLearner       -- 观察反馈 + 纠正写入 + 偏好更新
```

---

## 四、目录结构

```text
99-心迹回声桌宠Agent/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── docs/
│   ├── 项目设计.md
│   ├── 竞品拆解.md
│   ├── 情感算法设计.md        # E3-Score v0.2 心理学增强版
│   └── 思路任务书.md          # 每步做什么、为什么
│
├── src/
│   ├── config.py              # 全局配置
│   ├── persona/               # 人格引擎
│   │   └── engine.py
│   ├── memory/                # 双层记忆引擎
│   │   └── engine.py
│   ├── emotion/               # E3-Score 情感引擎
│   │   └── engine.py
│   ├── learning/              # 三层自学习
│   │   └── self_learner.py
│   ├── skills/                # 技能系统
│   │   ├── base.py
│   │   ├── hub.py
│   │   ├── comfort_skill.py
│   │   └── review_skill.py
│   ├── safety/                # 安全边界
│   │   └── guard.py
│   └── agent/                 # 决策主循环
│       └── orchestrator.py
│
├── data/
│   ├── raw/                   # 原始投喂资料（gitignore）
│   ├── personas/              # 人格配置文件（gitignore）
│   └── vector_store/          # 向量索引（gitignore）
│
├── notebooks/                 # 探索性实验
├── app/
│   ├── desktop/               # Tauri + React（Week 3）
│   └── service/               # FastAPI 服务（Week 3）
└── evals/                     # 评估资产（Week 4）
```

---

## 五、快速开始

```bash
# 1. 创建环境
conda create -n emoecho python=3.11
conda activate emoecho

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置
cp .env.example .env
# 编辑 .env 填入 API Key

# 4. 运行（Python 交互模式）
python -c "
from src.agent.orchestrator import AgentOrchestrator
agent = AgentOrchestrator()
# agent.load_persona('your_slug')  # 加载人格卡后使用
result = agent.chat('你好')
print(result.reply)
print(result.e3_score)
"
```

---

## 六、简历话术

> 从 0 到 1 设计并实现本地优先桌面数字人格 Agent，融合依恋理论/NVC/CBT/MI 四套心理学框架构建 E3-Score 情感策略路由算法，支持资料投喂人格构建、双层记忆混合检索、三层自学习（会话偏好/纠正记忆/周期微调）与可插拔技能系统；建立四级安全边界与完整评估闭环（人格一致性/记忆命中率/风险拦截率），完成桌面宠物化工程交付。
