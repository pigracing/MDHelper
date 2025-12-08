# 使用官方轻量级 Python 镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# 默认端口设置 (可以在运行时通过 -e PORT=xxx 覆盖)
ENV PORT=7860

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制主程序
COPY app.py .

# 创建必要的存储目录
RUN mkdir -p static/uploads static/temp_md

# 暴露端口 (Docker 文档用途，实际映射在 run 时指定)
EXPOSE $PORT

# 启动命令
# 注意：这里使用 Shell 格式 (不带 []) 以便解析 $PORT 变量
CMD gunicorn -w 4 -b 0.0.0.0:$PORT app:app