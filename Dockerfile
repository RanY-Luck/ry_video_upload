FROM mcr.microsoft.com/playwright:v1.41.0-jammy

# 设置工作目录
WORKDIR /app

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 换源 (使用阿里云镜像加速 apt)
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装系统依赖 (OpenCV 需要) & Python 环境
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    libgl1 \
    libglib2.0-0 \
    vim \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . .

# 处理 requirements.txt: 移除 pywin32 (Windows 特定库), 并在 Docker 中安装其余依赖
RUN grep -v "pywin32" requirements.txt > requirements-docker.txt && \
    python3 -m pip install --no-cache-dir -r requirements-docker.txt

# 确保日志和输出目录存在
RUN mkdir -p /app/logs /app/Upload/videos /app/Upload/cookies

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV DOCKER_CONTAINER=true
# 默认启用 Docker 模式 (Bark 扫码)
ENV DOCKER_MODE=true

# 运行命令
CMD ["python3", "standalone_upload.py"]
