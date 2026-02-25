#\!/bin/sh
set -e

echo "==> 启动时更新 chinesecalendar 库..."
pip install --upgrade --no-cache-dir chinese-calendar -q \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com
echo "==> 更新完成，启动 API 服务..."

exec uvicorn main:app --host 0.0.0.0 --port 8000
