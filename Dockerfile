# 使用轻量级 Python 基础镜像
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 防止 Python 生成 .pyc 文件，并让日志直接输出
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖 (如有需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml requirements.txt ./

# 安装依赖
# 注意：这里假设 thordata-sdk 已经发布到 PyPI。
# 如果是本地开发调试 Docker，通常需要挂载或者是从 Git 安装，
# 这里我们采用标准发布流程的写法。
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir .

# 复制源代码
COPY src/ src/

# 创建非 root 用户运行 (安全最佳实践)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# 设置入口点 (对应 pyproject.toml 中的 script)
ENTRYPOINT ["thordata-mcp"]