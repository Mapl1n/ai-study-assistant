# 📚 AI 学习助手 v2.1

> 全栈 AI 学习工具 — 桌面 GUI + Web 服务 + 手机 PWA，三端覆盖

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-teal.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED.svg)](https://www.docker.com/)
[![PWA](https://img.shields.io/badge/PWA-Ready-5A0FC8.svg)](https://web.dev/progressive-web-apps/)

<p align="center">
  <img src="https://img.shields.io/badge/Desktop-PySide6-41CD52?logo=qt" alt="Desktop">
  <img src="https://img.shields.io/badge/Web-FastAPI-009688?logo=fastapi" alt="Web">
  <img src="https://img.shields.io/badge/Mobile-PWA-FF5722?logo=pwa" alt="PWA">
  <img src="https://img.shields.io/badge/AI-DeepSeek-4B32C3?logo=openai" alt="AI">
</p>

---

## 🎯 项目概述

针对学生教材复习场景，开发的全平台 AI 学习助手。输入章节内容或上传 PDF 教材，自动生成**结构化考点清单**、**标准化练习题**和**分层级学习笔记**，帮助用户快速完成从"教材内容"到"复习资料"的转换。

### 核心功能

| 功能 | 桌面端 | Web端 | 手机PWA | 说明 |
|------|:---:|:---:|:---:|------|
| 📖 考点拆分 | ✅ | ✅ | ✅ | 拆分知识点，标注重要程度 ★★★ |
| 📝 生成题库 | ✅ | ✅ | ✅ | 选择/简答题，含答案和解析 |
| 📋 整理笔记 | ✅ | ✅ | ✅ | 结构化笔记，对比表格区分易混概念 |
| 💬 自由对话 | ✅ | ✅ | ✅ | 任意问题 AI 问答 |
| 📄 PDF 上传 | — | ✅ | ✅ | 上传教材 PDF 自动提取文字 |
| 📦 批量处理 | ✅ | — | — | 多个知识点一次性处理 |
| 📜 历史记录 | ✅ | ✅ | ✅ | JSON + SQLite 双存储方案 |
| 🔒 安全控制 | ✅ | ✅ | ✅ | 密码认证 + Token 鉴权 + IP 限流 |

---

## 🏗 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    用户层                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 桌面 GUI  │  │ 浏览器    │  │ 手机 PWA  │          │
│  │(PySide6) │  │(HTML/CSS) │  │(添加到桌面)│          │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘          │
│        │              │              │                │
│        └──────────────┼──────────────┘                │
│                       │                               │
│              ┌────────▼────────┐                      │
│              │   FastAPI 后端   │                      │
│              │  (REST + SSE)   │                      │
│              └────────┬────────┘                      │
│                       │                               │
│        ┌──────────────┼──────────────┐                │
│        │              │              │                │
│  ┌─────▼─────┐ ┌──────▼──────┐ ┌─────▼─────┐          │
│  │ SQLite DB  │ │ DeepSeek API│ │ 文件存储   │          │
│  │(历史/统计)  │ │ (AI 调用)   │ │(导出/缓存) │          │
│  └───────────┘ └─────────────┘ └───────────┘          │
│                                                       │
│              ┌────────────┴────────────┐              │
│              │   部署方式               │              │
│              │ Docker · ngrok · EXE    │              │
│              └─────────────────────────┘              │
└─────────────────────────────────────────────────────┘
```

---

## 🛠 技术栈

### 后端
- **FastAPI** — Web 框架，提供 RESTful API + SSE 流式推送
- **SQLite** — 数据库存储（历史记录、调用统计）
- **JWT Token** — 身份认证
- **PyPDF2** — PDF 文档解析

### 前端
- **PySide6 / Qt** — 桌面 GUI 应用
- **HTML5 + CSS3 + JavaScript** — Web 响应式前端
- **PWA** — Service Worker + Manifest，可安装到手机主屏幕

### AI
- **DeepSeek API** — 大语言模型调用
- **Prompt Engineering** — 自定义系统提示词模板
- **SSE（Server-Sent Events）** — 流式逐字输出

### DevOps
- **Docker + Docker Compose** — 一键部署
- **Git + GitHub** — 版本管理
- **ngrok** — 内网穿透公网访问
- **PyInstaller** — 打包独立 exe

---

## 🚀 快速开始

### 方式一：Docker 一键部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/Mapl1n/ai-study-assistant.git
cd ai-study-assistant

# 2. 配置 API Key
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入你的 DeepSeek API Key

# 3. 启动
docker compose up -d

# 4. 打开浏览器访问 http://localhost:8000
```

### 方式二：本地运行

```bash
# 1. 安装依赖
pip install -r backend/requirements.txt
pip install PySide6  # 桌面端需要

# 2. 配置 Key
cp backend/.env.example backend/.env
# 编辑 .env 填入 Key

# 3. 启动 Web 服务
cd backend && python app.py
# 访问 http://localhost:8000

# 4. 启动桌面端（可选）
python main.py
```

### 方式三：手机 PWA 安装

1. 手机浏览器打开 Web 服务地址
2. **iPhone**: Safari → 分享 → 添加到主屏幕
3. **Android**: Chrome → ⋮ → 添加到主屏幕 / 安装应用

---

## 📡 API 文档

启动服务后访问：`http://localhost:8000/docs`（Swagger 自动生成）

### 主要接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|:--:|
| POST | `/api/auth` | 密码验证，获取 Token | — |
| POST | `/api/chat` | 非流式 AI 对话 | Token |
| POST | `/api/chat/stream` | 流式 AI 对话（SSE） | Token |
| POST | `/api/upload/pdf` | 上传 PDF 并解析文字 | Token |
| POST | `/api/export` | 导出 Markdown/TXT | Token |
| GET | `/api/prompts` | 获取提示词模板 | — |
| GET | `/api/stats` | 今日调用统计 | Token |
| GET | `/api/history` | 历史记录查询 | Token |
| GET | `/api/health` | 健康检查 | — |

### 调用示例

```bash
# 1. 登录获取 Token
curl -X POST http://localhost:8000/api/auth \
  -H "Content-Type: application/json" \
  -d '{"password": "study2024"}'

# 2. 流式 AI 对话
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <你的Token>" \
  -d '{"prompt": "请拆分TCP/IP协议的考点", "mode": "考点拆分"}'
```

---

## 📁 项目结构

```
ai-study-assistant/
├── main.py                  # 桌面端 GUI（PySide6）
├── Dockerfile               # Docker 镜像
├── docker-compose.yml       # 一键部署编排
├── .dockerignore
├── .gitignore
├── README.md
├── backend/
│   ├── app.py               # FastAPI Web 服务 + PWA 前端
│   ├── core.py              # AI 调用 + PDF 解析 + 导出
│   ├── database.py          # SQLite 数据库模块
│   ├── .env.example         # API Key 配置模板
│   ├── .env                 # 实际密钥（Git 忽略）
│   ├── requirements.txt     # Python 依赖
│   └── __init__.py
└── data/                    # 用户数据（Git 忽略）
    ├── app.db               # SQLite 数据库
    ├── history.json         # 历史记录（旧版兼容）
    └── exports/             # 导出文件
```

---

## 🔒 安全设计

- **密钥保护**：API Key 通过 `.env` 文件管理，Git 排除，Docker 只读挂载
- **密码认证**：访问密码 → Token 鉴权，Token 使用 HMAC-SHA256 生成
- **频率限制**：内存级 IP 频率限制（默认 20次/天），防止滥用
- **无数据库依赖**：SQLite 嵌入式数据库，无需额外安装

---

## 📊 项目亮点

1. **全栈架构** — 独立完成从桌面 GUI → Web 后端 → 手机 PWA 的全平台开发
2. **流式输出** — SSE + QThread 多线程方案，AI 生成内容逐字实时展示
3. **工程化** — Docker 一键部署 + Git 版本管理 + PyInstaller 打包
4. **成本控制** — 三重安全机制保护 API Key 不被滥用
5. **Prompt 工程** — 定制化提示词模板，输出格式稳定可控

---

## 🔮 后续规划

- [ ] 用户注册/登录系统（多用户支持）
- [ ] 更多 AI 模型支持（OpenAI、Claude 等）
- [ ] 题目导入 Anki/Quizlet
- [ ] 语音输入支持
- [ ] 移动端原生 App（React Native）

---

## 📄 License

MIT © [Mapl1n](https://github.com/Mapl1n)

---

<p align="center">
  <sub>Built with ❤️ by Mapl1n | 2026</sub>
</p>
