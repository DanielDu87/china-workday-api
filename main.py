"""中国工作日校验 API"""

import importlib
import json
import logging
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import chinese_calendar
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from chinese_calendar import get_holiday_detail, is_workday
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

class CJKResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False).encode("utf-8")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

CACHE_DIR = Path("/app/cache")
CACHE_FILE = CACHE_DIR / "holidays_cache.json"
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# --- 辅助数据源 ---

NAGER_API = "https://date.nager.at/api/v3/PublicHolidays/{year}/CN"


def load_cache() -> dict:
    """加载本地缓存的辅助源数据"""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("缓存文件读取失败，忽略")
    return {}


def save_cache(data: dict):
    """保存辅助源数据到本地缓存"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


async def fetch_nager_holidays(year: int) -> dict[str, str]:
    """从 Nager.Date 获取指定年份的中国公共假日"""
    result = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(NAGER_API.format(year=year))
            if resp.status_code == 200:
                for item in resp.json():
                    result[item["date"]] = item["localName"]
                logger.info("Nager.Date %d 年数据获取成功，共 %d 条", year, len(result))
    except Exception as e:
        logger.warning("Nager.Date 数据获取失败: %s", e)
    return result


# --- 定时任务 ---


async def update_library():
    """更新 chinesecalendar 库并重新加载"""
    logger.info("开始定时更新 chinesecalendar...")
    try:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--no-cache-dir",
                "chinese-calendar",
                "-q",
                "-i",
                "https://mirrors.aliyun.com/pypi/simple/",
                "--trusted-host",
                "mirrors.aliyun.com",
            ]
        )
        importlib.reload(chinese_calendar)
        logger.info("chinesecalendar 更新并重载完成")
    except Exception as e:
        logger.error("更新失败: %s", e)


async def update_auxiliary_cache():
    """更新辅助源缓存"""
    logger.info("开始更新辅助源缓存...")
    current_year = date.today().year
    cache = load_cache()
    for year in [current_year, current_year + 1]:
        holidays = await fetch_nager_holidays(year)
        if holidays:
            cache[str(year)] = holidays
    save_cache(cache)
    logger.info("辅助源缓存更新完成")


# --- 核心逻辑 ---


def find_next_rest_day(from_date: date, max_days: int = 30) -> dict | None:
    """从指定日期开始，查找下一个休息日"""
    for i in range(1, max_days + 1):
        d = from_date + timedelta(days=i)
        try:
            if not is_workday(d):
                on_holiday, holiday_name = get_holiday_detail(d)
                return {
                    "date": d.isoformat(),
                    "weekday": WEEKDAY_NAMES[d.weekday()],
                    "detail": holiday_name if on_holiday and holiday_name else "周末",
                    "days_from_now": (d - date.today()).days,
                }
        except NotImplementedError:
            break
    return None


def get_date_status(target_date: date) -> dict:
    """获取指定日期的工作日状态"""
    is_work = is_workday(target_date)
    on_holiday, holiday_name = get_holiday_detail(target_date)
    weekday = target_date.weekday()
    weekday_name = WEEKDAY_NAMES[weekday]

    # 判断详细原因
    if on_holiday:
        detail = holiday_name or "法定节假日"
    elif is_work and weekday >= 5:
        detail = "调休补班"
    elif not is_work and weekday < 5:
        detail = "休息日"
    elif is_work:
        detail = "正常工作日"
    else:
        detail = "周末"

    # 辅助源比对
    warning = None
    cache = load_cache()
    year_cache = cache.get(str(target_date.year), {})
    date_str = target_date.isoformat()

    if year_cache:
        in_nager = date_str in year_cache
        # Nager 只包含公共假日，如果主源说是假日但辅助源没有，或反过来，给出提示
        if on_holiday and not in_nager:
            warning = "数据源存在差异，请以官方通知为准"
        elif not on_holiday and in_nager:
            warning = "数据源存在差异，请以官方通知为准"

    result = {
        "date": date_str,
        "weekday": weekday_name,
        "is_workday": is_work,
        "detail": detail,
        "next_rest_day": find_next_rest_day(target_date),
        "warning": warning,
    }
    if on_holiday and holiday_name:
        result["holiday_name"] = holiday_name
    return result


# --- FastAPI 应用 ---

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时更新辅助源缓存
    await update_auxiliary_cache()
    # 每天凌晨 4:00 执行更新
    scheduler.add_job(update_library, "cron", hour=4, minute=0)
    scheduler.add_job(update_auxiliary_cache, "cron", hour=4, minute=5)
    scheduler.start()
    logger.info("定时任务已启动，每天 04:00 自动更新")
    yield
    scheduler.shutdown()


app = FastAPI(
    title="中国工作日校验 API",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=CJKResponse,
    docs_url="/workday/docs",
    redoc_url="/workday/redoc",
    openapi_url="/workday/openapi.json"
)


@app.get("/workday")
def workday_index():
    return RedirectResponse(url="https://api.dyxcloud.com/workday/docs")


@app.get("/workday/check")
def check_default():
    """默认返回今天和明天的工作日状态"""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_status = get_date_status(today)
    tomorrow_status = get_date_status(tomorrow)
    today_status.pop("next_rest_day", None)
    tomorrow_status.pop("next_rest_day", None)
    return {
        "today": today_status,
        "tomorrow": tomorrow_status,
        "next_rest_day": find_next_rest_day(today),
    }


@app.get("/workday/check/today")
def check_today():
    """返回今天的工作日状态"""
    today = date.today()
    status = get_date_status(today)
    status.pop("next_rest_day", None)
    return {
        "today": status,
        "next_rest_day": find_next_rest_day(today),
    }


@app.get("/workday/check/tomorrow")
def check_tomorrow():
    """返回明天的工作日状态"""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    status = get_date_status(tomorrow)
    status.pop("next_rest_day", None)
    return {
        "tomorrow": status,
        "next_rest_day": find_next_rest_day(today),
    }


@app.get("/workday/check/{target_date}")
def check_date(target_date: str):
    """查询指定日期是否为工作日，支持多种格式：
    - 2026-02-25、2026-2-25
    - 2026_02_25、2026_2_25
    - 20260225
    - 2026年02月25日、2026年2月25日
    """
    # 支持的日期格式列表
    formats = [
        "%Y-%m-%d", "%Y-%-m-%-d",
        "%Y_%m_%d", "%Y_%-m_%-d",
        "%Y%m%d",
        "%Y年%m月%d日", "%Y年%-m月%-d日",
    ]

    d = None
    for fmt in formats:
        try:
            d = datetime.strptime(target_date, fmt).date()
            break
        except ValueError:
            continue

    if d is None:
        raise HTTPException(
            status_code=400,
            detail="日期格式错误，支持格式：2026-02-25、2026_02_25、20260225、2026年02月25日等"
        )

    try:
        status = get_date_status(d)
        status.pop("next_rest_day", None)
        return {
            "date": status,
            "next_rest_day": find_next_rest_day(date.today()),
        }
    except NotImplementedError:
        raise HTTPException(
            status_code=400,
            detail=f"暂不支持查询 {d.year} 年的数据，chinesecalendar 库尚未收录",
        )
