import sys
import requests
import json
import os
import re
from datetime import datetime

# 尝试从 .env 文件加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass  # python-dotenv 可选，没有的话手动设环境变量即可

# ========== 配置 ==========
# 从环境变量读取 API Key（不要在代码里写真实 Key！）
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "你的DeepSeek-API-Key")
API_URL = "https://api.deepseek.com/v1/chat/completions"

# 数据存储目录
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)


# ========== AI流式调用 ==========
def call_ai_stream(prompt, system_prompt="", callback=None):
    """流式调用AI，逐字返回结果"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "stream": True
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=data, stream=True, timeout=60)
        if resp.status_code == 200:
            full_content = ""
            for line in resp.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        line = line[6:]
                        if line == '[DONE]':
                            break
                        try:
                            chunk = json.loads(line)
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    content = delta['content']
                                    full_content += content
                                    if callback:
                                        callback(content)
                        except json.JSONDecodeError:
                            continue
            return full_content
        else:
            return f"❌ 请求失败：{resp.status_code}"
    except Exception as e:
        return f"❌ 网络错误：{e}"


# ========== 非流式AI调用 ==========
def call_ai(prompt, system_prompt=""):
    """调用 DeepSeek API（非流式）"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "stream": False
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=data, timeout=30)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            return f"请求失败：{resp.status_code}"
    except Exception as e:
        return f"网络错误：{e}"


# ========== 系统提示词模板 ==========
SYSTEM_PROMPTS = {
    "考点拆分": "你是一位经验丰富的学科教师。请根据用户提供的章节内容，拆分知识点，梳理考点，建立知识框架。输出格式：Markdown层级列表，每个知识点标注重要程度（★/★★/★★★）。",
    "生成题库": "你是一位命题老师。请根据用户提供的知识点，生成标准化练习题。题型包含选择题和简答题。每道题包含题干、选项（选择题）、答案和详细解析。输出格式：Markdown表格。",
    "整理笔记": "你是一位学习笔记整理专家。请将用户提供的原始内容整理成结构清晰的学习笔记，提取核心知识点，用对比表格区分易混淆概念，标注重点。输出格式：Markdown层级列表。"
}


# ========== 导出功能 ==========
# ========== PDF 解析 ==========
def parse_pdf(file_path):
    """解析 PDF 文件，返回全部文本内容"""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append(f"--- 第 {i+1} 页 ---\n{text}")
        return "\n\n".join(pages) if pages else "⚠️ PDF 中没有提取到文字（可能是扫描版图片PDF）"
    except ImportError:
        return "❌ 缺少 PyPDF2 库，请执行: pip install PyPDF2"
    except Exception as e:
        return f"❌ PDF 解析失败：{e}"


def parse_pdf_from_bytes(data, filename=""):
    """从字节数据解析 PDF（用于上传接口）"""
    import tempfile
    tmp_path = None
    try:
        # PyPDF2 需要类文件对象，直接包装 bytes
        from PyPDF2 import PdfReader
        from io import BytesIO
        reader = PdfReader(BytesIO(data))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append(f"--- 第 {i+1} 页 ---\n{text}")
        return "\n\n".join(pages) if pages else "⚠️ PDF 中没有提取到文字（可能是扫描版图片PDF）"
    except ImportError:
        return "❌ 缺少 PyPDF2 库，请执行: pip install PyPDF2"
    except Exception as e:
        return f"❌ PDF 解析失败：{e}"


def export_result(content, export_type="markdown"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if export_type == "markdown":
        filename = os.path.join(EXPORT_DIR, f"export_{timestamp}.md")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        filename = os.path.join(EXPORT_DIR, f"export_{timestamp}.txt")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(re.sub(r'[#*_`>-]', '', content))
    return filename
