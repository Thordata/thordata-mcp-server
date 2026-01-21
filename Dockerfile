# 使用官方轻量级 Python 镜像
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 环境变量：防止 pyc 生成，让日志立即输出
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装 git (如果 mcp 依赖需要 git) 和基础工具
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml .
COPY src/ src/

# 安装项目 (自动从 PyPI 拉取 thordata-sdk)
RUN pip install --no-cache-dir .

# 创建非 root 用户 (安全)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# 启动命令
ENTRYPOINT ["thordata-mcp"]