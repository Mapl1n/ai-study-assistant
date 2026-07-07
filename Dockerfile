# ===== AI学习助手 v2.0 — Docker 镜像 =====
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY backend/ ./backend/
COPY main.py .

# 创建数据目录
RUN mkdir -p /app/data/exports

# 暴露端口
EXPOSE 8000

# 环境变量（部署时通过 docker-compose 或 -e 传入真实 Key）
ENV DEEPSEEK_API_KEY=你的DeepSeek-API-Key

# 启动 Web 服务
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
