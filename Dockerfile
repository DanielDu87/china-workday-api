# --- 构建阶段 ---
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com

# --- 运行阶段 ---
FROM python:3.11-slim

WORKDIR /app

# 从构建阶段复制已安装的依赖
COPY --from=builder /install /usr/local

COPY main.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# 创建缓存目录
RUN mkdir -p /app/cache

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "./entrypoint.sh"]
