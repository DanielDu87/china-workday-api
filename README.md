# China Workday API

中国工作日查询 API，基于 [chinese-calendar](https://github.com/LKI/chinese-calendar) 库，支持法定节假日、调休补班识别，并通过 Nager.Date 辅助源进行数据交叉验证。

## 功能

- 查询任意日期是否为工作日
- 识别法定节假日、调休补班、周末
- 返回下一个休息日信息
- 双数据源交叉验证，数据存在差异时给出警告
- 每天凌晨 4:00 自动更新 `chinese-calendar` 库

## 接口

### 查询今天和明天

```
GET /check/tomorrow
```

响应示例：

```json
{
 "today": {
  "date": "2026-02-25",
  "weekday": "周三",
  "is_workday": true,
  "detail": "正常工作日"
 },
 "tomorrow": {
  "date": "2026-02-26",
  "weekday": "周四",
  "is_workday": true,
  "detail": "正常工作日"
 },
 "next_rest_day": {
  "date": "2026-02-28",
  "weekday": "周六",
  "detail": "周末",
  "days_from_now": 3
 }
}
```

### 查询指定日期

```
GET /check/{YYYY-MM-DD}
```

响应示例：

```json
{
  "date": "2026-01-01",
  "weekday": "周四",
  "is_workday": false,
  "detail": "元旦",
  "holiday_name": "元旦",
  "next_rest_day": { ... }
}
```

## 部署

### Docker Compose（推荐）

```bash
docker compose up -d
```

服务默认监听 `8000` 端口，缓存数据持久化到 `cache-data` volume。

### 本地运行

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 技术栈

- [FastAPI](https://fastapi.tiangolo.com/)
- [chinese-calendar](https://github.com/LKI/chinese-calendar)
- [APScheduler](https://apscheduler.readthedocs.io/)
- [httpx](https://www.python-httpx.org/)
