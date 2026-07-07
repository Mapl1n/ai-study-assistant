from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
import json
import queue
import threading
import time
import hashlib
import hmac
from collections import defaultdict
import uvicorn

# 导入核心业务逻辑
from core import call_ai, call_ai_stream, SYSTEM_PROMPTS, parse_pdf_from_bytes

# ========== 安全配置 ==========
ACCESS_PASSWORD = "study2024"      # 访问密码（修改为你自己的）
DAILY_LIMIT = 20                    # 每 IP 每天最大请求次数

# IP 频率限制（内存记录）
_ip_usage = defaultdict(list)       # {ip: [timestamp, ...]}

def check_rate_limit(ip: str) -> bool:
    """检查 IP 是否超过每日限制，返回 True 表示允许"""
    now = time.time()
    cutoff = now - 86400  # 24 小时前
    _ip_usage[ip] = [t for t in _ip_usage[ip] if t > cutoff]  # 清理过期记录
    if len(_ip_usage[ip]) >= DAILY_LIMIT:
        return False
    _ip_usage[ip].append(now)
    return True

def make_token(password: str) -> str:
    """根据密码生成简单 token"""
    return hashlib.sha256(f"{password}:salt2024".encode()).hexdigest()[:16]

def check_auth(request: Request) -> bool:
    """验证请求中的 token 或密码"""
    token = request.headers.get("X-Auth-Token", "")
    expected = make_token(ACCESS_PASSWORD)
    return token == expected

# ========== 创建 FastAPI 应用 ==========
app = FastAPI(
    title="AI学习助手 API",
    description="AI学习助手后端服务，支持考点拆分、生成题库、整理笔记、自由对话、PDF上传",
    version="2.0.0"
)

# ========== 允许跨域 ==========
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 请求模型 ==========
class ChatRequest(BaseModel):
    prompt: str
    mode: Optional[str] = "自由对话"

class AuthRequest(BaseModel):
    password: str


# ========== 认证接口 ==========
@app.post("/api/auth")
async def auth(req: AuthRequest):
    """密码验证，返回访问 token"""
    if req.password == ACCESS_PASSWORD:
        token = make_token(req.password)
        return {"success": True, "token": token}
    return {"success": False, "message": "密码错误"}


# ========== 认证检查 ==========
def _guard(req: Request):
    """验证身份 + 频率限制，失败时返回 None（表示错误响应）"""
    if not check_auth(req):
        return {"success": False, "result": "🔒 未授权，请先输入访问密码"}
    ip = req.client.host if req.client else "unknown"
    if not check_rate_limit(ip):
        return {"success": False, "result": f"⏰ 今日请求已达上限（{DAILY_LIMIT}次/天），请明天再试"}
    return None  # 通过


# ========== 非流式接口 ==========
@app.post("/api/chat")
async def chat(req: Request, data: ChatRequest):
    """通用对话接口（非流式）"""
    if err := _guard(req): return err
    try:
        system_prompt = SYSTEM_PROMPTS.get(data.mode, "")
        result = call_ai(data.prompt, system_prompt)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/split_knowledge")
async def split_knowledge(req: Request, data: ChatRequest):
    """拆分考点"""
    if err := _guard(req): return err
    try:
        prompt = f"请拆分以下章节的考点，梳理知识框架：\n\n{data.prompt}"
        result = call_ai(prompt, SYSTEM_PROMPTS["考点拆分"])
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate_questions")
async def generate_questions(req: Request, data: ChatRequest):
    """生成题库"""
    if err := _guard(req): return err
    try:
        prompt = f"请根据以下知识点生成标准化练习题：\n\n{data.prompt}"
        result = call_ai(prompt, SYSTEM_PROMPTS["生成题库"])
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/organize_notes")
async def organize_notes(req: Request, data: ChatRequest):
    """整理笔记"""
    if err := _guard(req): return err
    try:
        prompt = f"请将以下内容整理成结构化学习笔记：\n\n{data.prompt}"
        result = call_ai(prompt, SYSTEM_PROMPTS["整理笔记"])
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 流式接口（SSE）==========
@app.post("/api/chat/stream")
async def chat_stream(req: Request, data: ChatRequest):
    """通用对话接口（流式，逐字返回）"""
    if err := _guard(req): return err
    system_prompt = SYSTEM_PROMPTS.get(data.mode, "")

    def generate():
        q = queue.Queue()

        def on_token(token: str):
            q.put(token)

        def run():
            call_ai_stream(data.prompt, system_prompt, callback=on_token)
            q.put(None)

        threading.Thread(target=run, daemon=True).start()

        while True:
            token = q.get()
            if token is None:
                break
            yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ========== PDF 上传接口 ==========
@app.post("/api/upload/pdf")
async def upload_pdf(req: Request, file: UploadFile = File(...), mode: str = Form(default="自由对话")):
    """上传 PDF 文件，返回解析后的文本"""
    if err := _guard(req): return err
    if not file.filename.lower().endswith(".pdf"):
        return {"success": False, "result": "⚠️ 仅支持 PDF 文件"}

    try:
        data = await file.read()
        text = parse_pdf_from_bytes(data, file.filename)
        if text.startswith("❌"):
            return {"success": False, "result": text}
        return {"success": True, "result": text, "filename": file.filename}
    except Exception as e:
        return {"success": False, "result": f"❌ 上传失败：{e}"}


# ========== 导出接口 ==========
@app.post("/api/export")
async def export_result(content: str = Query(...), export_type: str = "markdown"):
    """导出结果到文件"""
    from core import export_result as do_export
    path = do_export(content, export_type)
    return {"success": True, "result": path}


# ========== 获取提示词模板 ==========
@app.get("/api/prompts")
async def get_prompts():
    return {"success": True, "result": SYSTEM_PROMPTS}


# ========== 健康检查 ==========
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "AI学习助手后端服务运行正常"}


# ========== PWA 配置 ==========
@app.get("/manifest.json")
async def manifest():
    """PWA 清单文件 — 让手机识别为 App"""
    return {
        "name": "AI 学习助手",
        "short_name": "学习助手",
        "description": "考点拆分 · 生成题库 · 整理笔记 · PDF上传",
        "start_url": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f0f2f5",
        "theme_color": "#3498db",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }


@app.get("/sw.js")
async def service_worker():
    """Service Worker — 离线缓存支持"""
    return HTMLResponse(content=SW_JS, media_type="application/javascript")


# ========== 前端页面（PC + 手机自适应）==========
@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=HTML_PAGE)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>📚 AI 学习助手</title>

<!-- PWA Meta Tags -->
<link rel="manifest" href="/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="AI学习助手">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#3498db">
<meta name="application-name" content="AI学习助手">

<!-- Apple Touch Icons (使用 SVG 内联生成，无需外部文件) -->
<link rel="apple-touch-icon" href="/icon-192.png">
<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="/icon-512.png">
<style>
  :root {
    --primary: #3498db;
    --purple: #9b59b6;
    --green: #27ae60;
    --red: #e74c3c;
    --bg: #f0f2f5;
    --card: #fff;
    --text: #2c3e50;
    --border: #dcdfe6;
    --radius: 12px;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    -webkit-tap-highlight-color: transparent;
  }
  .container { max-width: 800px; margin: 0 auto; padding: 12px; }

  .header {
    text-align: center; padding: 18px 0 8px;
  }
  .header h1 { font-size: 26px; }
  .header p { color: #909399; font-size: 13px; margin-top: 4px; }

  .card {
    background: var(--card);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,.04);
  }
  .card label {
    display: block;
    font-weight: 600; font-size: 14px;
    margin-bottom: 8px;
  }

  /* 模式按钮 */
  .mode-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .mode-btn {
    flex: 1; min-width: 60px;
    padding: 10px 6px;
    border: 2px solid var(--border);
    border-radius: 8px;
    background: #fff;
    cursor: pointer;
    font-size: 13px; text-align: center;
    transition: all .2s;
    user-select: none;
  }
  .mode-btn:active { transform: scale(.96); }
  .mode-btn.active {
    border-color: var(--primary);
    background: #ecf5ff;
    color: var(--primary);
    font-weight: 700;
  }

  /* 输入框 */
  textarea {
    width: 100%; min-height: 150px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px; font-size: 14px;
    font-family: inherit; line-height: 1.7;
    resize: vertical;
  }
  textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px rgba(52,152,219,.15); }

  /* 上传区 */
  .upload-zone {
    border: 2px dashed var(--border);
    border-radius: var(--radius);
    padding: 18px; margin-top: 12px;
    text-align: center; cursor: pointer;
    transition: all .2s;
    background: #fafbfc;
  }
  .upload-zone:active, .upload-zone.drag { border-color: var(--primary); background: #ecf5ff; }
  .upload-zone .icon { font-size: 32px; }
  .upload-zone p { font-size: 12px; color: #909399; margin-top: 4px; }
  .upload-zone .file-name { color: var(--primary); font-weight: 600; font-size: 13px; margin-top: 6px; }

  /* 按钮 */
  .btn-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  .btn {
    padding: 10px 20px; border: none;
    border-radius: 8px; font-size: 14px;
    font-weight: 600; cursor: pointer;
    transition: all .2s; user-select: none;
    display: inline-flex; align-items: center; gap: 4px;
  }
  .btn:active { transform: scale(.96); }
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:disabled { background: #a0cfff; }
  .btn-outline { background: #fff; color: var(--primary); border: 2px solid var(--primary); }

  /* 输出区 */
  #output {
    min-height: 200px; max-height: 450px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px; background: #fafbfc;
    font-size: 14px; line-height: 1.8;
    white-space: pre-wrap; word-break: break-word;
  }
  #output:empty::before { content: "AI 生成的内容将在这里显示..."; color: #c0c4cc; }

  .status-bar { text-align: center; font-size: 12px; padding: 6px; color: #909399; }
  .status-bar.thinking { color: #e6a23c; }
  .status-bar.done { color: var(--green); }

  /* 手机适配 */
  @media (max-width: 600px) {
    .header h1 { font-size: 22px; }
    .card { padding: 12px; border-radius: 10px; }
    .mode-btn { font-size: 12px; padding: 8px 4px; }
    .btn { font-size: 13px; padding: 10px 14px; }
    textarea { min-height: 120px; font-size: 16px; } /* 防止 iOS 缩放 */
    #output { max-height: 350px; }
  }

  /* 登录遮罩 */
  .login-overlay {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: var(--bg); display: flex; align-items: center; justify-content: center;
    z-index: 9999;
  }
  .login-overlay.hidden { display: none; }
  .login-box {
    background: var(--card); border-radius: 16px;
    padding: 32px 24px; text-align: center;
    box-shadow: 0 8px 32px rgba(0,0,0,.1);
    max-width: 360px; width: 90%;
  }
  .login-box h2 { font-size: 22px; margin-bottom: 6px; }
  .login-box p { color: #909399; font-size: 13px; margin-bottom: 20px; }
  .login-box input {
    width: 100%; padding: 12px; border: 2px solid var(--border);
    border-radius: 10px; font-size: 16px; text-align: center; margin-bottom: 12px;
  }
  .login-box input:focus { outline: none; border-color: var(--primary); }
  .login-box .hint { color: var(--red); font-size: 12px; min-height: 18px; }

  /* 安装横幅 */
  .install-banner {
    position: fixed; bottom: 0; left: 0; width: 100%;
    background: #2c3e50; color: #fff;
    padding: 14px 18px;
    display: flex; align-items: center; justify-content: space-between;
    z-index: 9998;
    transform: translateY(100%);
    transition: transform .3s;
  }
  .install-banner.show { transform: translateY(0); }
  .install-banner .text { font-size: 14px; flex: 1; }
  .install-banner .text strong { color: #f1c40f; }
  .install-banner button {
    padding: 8px 18px; border: none; border-radius: 6px;
    font-size: 14px; font-weight: 600; cursor: pointer; margin-left: 10px;
  }
  .btn-install { background: #f1c40f; color: #2c3e50; }
  .btn-close { background: transparent; color: #fff; font-size: 18px; }
</style>
</head>
<body>

<!-- 登录遮罩 -->
<div class="login-overlay" id="loginOverlay">
  <div class="login-box">
    <h2>🔒 AI 学习助手</h2>
    <p>请输入访问密码</p>
    <input type="password" id="pwdInput" placeholder="输入密码" autocomplete="off">
    <div class="hint" id="loginHint"></div>
    <button class="btn btn-primary" id="btnLogin" style="width:100%">🚀 进入</button>
  </div>
</div>

<!-- 安装横幅 -->
<div class="install-banner" id="installBanner">
  <span class="text">📲 添加到主屏幕，像 <strong>App</strong> 一样使用</span>
  <button class="btn-install" id="btnInstall">安装</button>
  <button class="btn-close" id="btnCloseBanner">✕</button>
</div>

<div class="container">
  <div class="header">
    <h1>📚 AI 学习助手</h1>
    <p>考点拆分 · 生成题库 · 整理笔记 · 自由对话 · PDF 上传</p>
  </div>

  <!-- 模式选择 -->
  <div class="card">
    <label>🎯 选择功能</label>
    <div class="mode-row" id="modeRow">
      <button class="mode-btn active" data-mode="考点拆分">📖 考点拆分</button>
      <button class="mode-btn" data-mode="生成题库">📝 生成题库</button>
      <button class="mode-btn" data-mode="整理笔记">📋 整理笔记</button>
      <button class="mode-btn" data-mode="自由对话">💬 自由对话</button>
    </div>
  </div>

  <!-- 输入区 -->
  <div class="card">
    <label>✏️ 输入内容</label>
    <textarea id="inputText" placeholder="粘贴章节内容、知识点或输入问题...&#10;&#10;💡 也可以上传 PDF 自动填充"></textarea>

    <div class="upload-zone" id="uploadZone">
      <div class="icon">📄</div>
      <p>点击上传 PDF（自动解析文字）</p>
      <input type="file" id="fileInput" accept=".pdf" style="display:none">
      <div class="file-name" id="fileName"></div>
    </div>

    <div class="btn-row">
      <button class="btn btn-primary" id="btnSubmit">🚀 提交</button>
      <button class="btn btn-outline" id="btnClear">🗑 清空</button>
    </div>
  </div>

  <!-- 输出区 -->
  <div class="card">
    <label>📤 输出结果</label>
    <div id="output"></div>
    <div class="status-bar" id="status">✅ 就绪</div>
    <div class="btn-row">
      <button class="btn btn-outline" id="btnExportMd">📥 导出 Markdown</button>
      <button class="btn btn-outline" id="btnExportTxt">📥 导出 TXT</button>
    </div>
  </div>
</div>

<script>
// ========== 全局状态 ==========
let currentMode = "考点拆分";
let authToken = localStorage.getItem("authToken") || "";

// ========== 登录逻辑 ==========
const loginOverlay = document.getElementById("loginOverlay");
const pwdInput = document.getElementById("pwdInput");
const loginHint = document.getElementById("loginHint");

// 检查是否已登录
if (authToken) {
  loginOverlay.classList.add("hidden");
}

async function doLogin() {
  const pwd = pwdInput.value.trim();
  if (!pwd) { loginHint.textContent = "请输入密码"; return; }
  try {
    const r = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pwd })
    });
    const j = await r.json();
    if (j.success) {
      authToken = j.token;
      localStorage.setItem("authToken", authToken);
      loginOverlay.classList.add("hidden");
    } else {
      loginHint.textContent = "❌ 密码错误";
    }
  } catch (e) {
    loginHint.textContent = "网络错误，请重试";
  }
}

document.getElementById("btnLogin").addEventListener("click", doLogin);
pwdInput.addEventListener("keydown", e => { if (e.key === "Enter") doLogin(); });

// 统一 fetch 封装（自动带 token）
function api(url, options = {}) {
  options.headers = options.headers || {};
  options.headers["X-Auth-Token"] = authToken;
  return fetch(url, options);
}

// ========== 模式切换 ==========
document.querySelectorAll(".mode-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
  });
});

// === PDF 上传 ===
const uploadZone = document.getElementById("uploadZone");
const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const inputText = document.getElementById("inputText");

uploadZone.addEventListener("click", () => fileInput.click());
uploadZone.addEventListener("dragover", e => { e.preventDefault(); uploadZone.classList.add("drag"); });
uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("drag"));
uploadZone.addEventListener("drop", e => {
  e.preventDefault(); uploadZone.classList.remove("drag");
  const f = e.dataTransfer.files[0];
  if (f) uploadPdf(f);
});
fileInput.addEventListener("change", () => {
  const f = fileInput.files[0];
  if (f) uploadPdf(f);
});

async function uploadPdf(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) { alert("仅支持 PDF 文件"); return; }
  fileName.textContent = "⏳ 解析中...";
  const fd = new FormData();
  fd.append("file", file);
  fd.append("mode", currentMode);
  try {
    const r = await api("/api/upload/pdf", { method: "POST", body: fd });
    const j = await r.json();
    if (j.success) {
      inputText.value = j.result;
      fileName.textContent = "✅ " + j.filename + "（" + j.result.length + " 字）";
    } else {
      fileName.textContent = j.result;
    }
  } catch (e) {
    fileName.textContent = "上传失败: " + e.message;
  }
}

// === 流式提交 ===
const output = document.getElementById("output");
const status = document.getElementById("status");
const btnSubmit = document.getElementById("btnSubmit");

btnSubmit.addEventListener("click", async () => {
  const prompt = inputText.value.trim();
  if (!prompt) { alert("请先输入内容或上传 PDF"); return; }

  btnSubmit.disabled = true;
  btnSubmit.textContent = "⏳ 处理中...";
  status.textContent = "⏳ AI 思考中...";
  status.className = "status-bar thinking";
  output.textContent = "";

  try {
    const r = await api("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, mode: currentMode })
    });
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const d = line.slice(6);
          if (d === "[DONE]") continue;
          try { output.textContent += JSON.parse(d).token; } catch(e){}
        }
      }
      output.scrollTop = output.scrollHeight;
    }
    status.textContent = "✅ 完成";
    status.className = "status-bar done";
  } catch (e) {
    output.textContent = "❌ 网络错误：" + e.message;
    status.textContent = "❌ 出错了";
  }
  btnSubmit.disabled = false;
  btnSubmit.textContent = "🚀 提交";
});

// === 清空 ===
document.getElementById("btnClear").addEventListener("click", () => {
  inputText.value = "";
  output.textContent = "";
  fileName.textContent = "";
  status.textContent = "✅ 就绪";
  status.className = "status-bar";
});

// === 导出 ===
document.getElementById("btnExportMd").addEventListener("click", () => doExport("markdown"));
document.getElementById("btnExportTxt").addEventListener("click", () => doExport("txt"));

async function doExport(type) {
  const c = output.textContent.trim();
  if (!c) { alert("没有内容可导出"); return; }
  const r = await api("/api/export?content=" + encodeURIComponent(c) + "&export_type=" + type, { method: "POST" });
  const j = await r.json();
  status.textContent = j.success ? "✅ 已导出" : "导出失败";
  status.className = "status-bar done";
}

// ========== PWA 安装横幅 ==========
let deferredPrompt = null;
const installBanner = document.getElementById("installBanner");

window.addEventListener("beforeinstallprompt", e => {
  e.preventDefault();
  deferredPrompt = e;
  installBanner.classList.add("show");
});

document.getElementById("btnInstall").addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  console.log("PWA install:", outcome);
  deferredPrompt = null;
  installBanner.classList.remove("show");
});

document.getElementById("btnCloseBanner").addEventListener("click", () => {
  installBanner.classList.remove("show");
});
</script>

<script>
// ========== 注册 Service Worker（PWA 离线缓存）==========
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js')
    .then(reg => console.log('✅ SW registered:', reg.scope))
    .catch(err => console.log('⚠️ SW failed:', err));
}
</script>
</body>
</html>"""


# ========== Service Worker 脚本 ==========
SW_JS = r"""
const CACHE_NAME = 'ai-study-v2';
const URLS_TO_CACHE = [
  '/',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

// 安装：预缓存关键资源
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(URLS_TO_CACHE))
  );
  self.skipWaiting();
});

// 激活：清理旧缓存
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 请求拦截：缓存优先，API 请求走网络
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/')) {
    // API 请求：仅网络
    event.respondWith(fetch(event.request));
  } else {
    // 静态资源：缓存优先，网络回退
    event.respondWith(
      caches.match(event.request).then(cached =>
        cached || fetch(event.request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        })
      )
    );
  }
});
"""


# ========== PWA 图标生成（纯色 PNG，无需外部文件）==========
import struct
import zlib

def _make_png(size, color=(52, 152, 219)):
    """生成纯色方形 PNG"""
    r, g, b = color

    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    raw = b''
    for y in range(size):
        raw += b'\x00'
        for x in range(size):
            raw += bytes([r, g, b, 255])

    return (
        b'\x89PNG\r\n\x1a\n' +
        chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) +
        chunk(b'IDAT', zlib.compress(raw)) +
        chunk(b'IEND', b'')
    )


@app.get("/icon-192.png")
async def icon_192():
    from fastapi.responses import Response
    return Response(content=_make_png(192), media_type="image/png")


@app.get("/icon-512.png")
async def icon_512():
    from fastapi.responses import Response
    return Response(content=_make_png(512), media_type="image/png")


# ========== 启动入口 ==========
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
