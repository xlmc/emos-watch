from __future__ import annotations

import json
import os
import random
import re
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
MAPPING_PATH = ROOT / "mapping.json"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
CACHE_PATH = DATA_DIR / "mapping-cache.json"
WATCH_PATH = ROOT / "watch.json"
COVER_PATH = ROOT / "cover.jpg"

DOUBAN_URL = "https://m.douban.com/rexxar/api/v2/subject/recent_hot/tv"
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/tv"
TMDB_TV_URL = "https://api.themoviedb.org/3/tv"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Referer": "https://m.douban.com/tv/",
}


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_title(value: str) -> str:
    value = value.lower().replace("（", "(").replace("）", ")")
    value = re.sub(r"第[一二三四五六七八九十百0-9]+季", "", value)
    value = re.sub(r"season\s*[0-9]+", "", value, flags=re.I)
    return re.sub(r"[^\w\u4e00-\u9fff]", "", value)


def get_year(subject: dict) -> int | None:
    match = re.match(r"(\d{4})", subject.get("card_subtitle", ""))
    return int(match.group(1)) if match else None


def fetch_douban_top(limit: int) -> list[dict]:
    response = requests.get(
        DOUBAN_URL,
        params={"start": 0, "limit": limit, "category": "热门", "type": "tv_domestic"},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items", [])
    if len(items) < limit:
        raise RuntimeError(f"豆瓣返回 {len(items)} 条，少于要求的候选数量 {limit} 条")
    return [
        {
            "douban_id": str(item["id"]),
            "title": item["title"],
            "year": get_year(item),
            "douban_rank": index + 1,
            "douban_url": f"https://movie.douban.com/subject/{item['id']}/",
        }
        for index, item in enumerate(items[:limit])
    ]


def tmdb_headers() -> dict:
    token = os.environ.get("TMDB_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 GitHub Actions Secret: TMDB_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def choose_tmdb_result(subject: dict, results: list[dict]) -> dict | None:
    if not results:
        return None
    source_title = normalize_title(subject["title"])
    source_year = subject.get("year")

    def score(result: dict) -> tuple[int, float]:
        candidate_title = normalize_title(result.get("name", ""))
        candidate_year = (result.get("first_air_date") or "")[:4]
        value = float(result.get("popularity") or 0)
        points = 0
        if candidate_title == source_title:
            points += 100
        elif source_title in candidate_title or candidate_title in source_title:
            points += 45
        if source_year and candidate_year == str(source_year):
            points += 35
        if result.get("poster_path"):
            points += 5
        return points, value

    return max(results, key=score) if results else None


def resolve_tmdb(subject: dict, headers: dict, manual: dict, cache: dict) -> dict | None:
    douban_id = subject["douban_id"]
    if douban_id in manual:
        return {"id": int(manual[douban_id]), "name": subject["title"], "poster_path": None}
    if douban_id in cache:
        return cache[douban_id]

    params = {"query": subject["title"], "language": "zh-CN", "include_adult": "false", "page": 1}
    if subject.get("year"):
        params["first_air_date_year"] = subject["year"]
    response = requests.get(TMDB_SEARCH_URL, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    result = choose_tmdb_result(subject, response.json().get("results", []))

    # A year-filtered search can miss older or differently dated entries.
    if not result and "first_air_date_year" in params:
        params.pop("first_air_date_year")
        response = requests.get(TMDB_SEARCH_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        result = choose_tmdb_result(subject, response.json().get("results", []))

    if not result:
        return None
    details = requests.get(f"{TMDB_TV_URL}/{result['id']}", params={"language": "zh-CN"}, headers=headers, timeout=30)
    details.raise_for_status()
    data = details.json()
    resolved = {"id": int(data["id"]), "name": data.get("name", subject["title"]), "poster_path": data.get("poster_path")}
    cache[douban_id] = resolved
    return resolved


def get_font(size: int):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def download_poster(poster_path: str) -> Image.Image:
    response = requests.get(f"{TMDB_IMAGE_BASE}{poster_path}", timeout=30)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")


def make_cover(selected: list[dict], now: datetime):
    width, height = 1600, 900
    canvas = Image.new("RGB", (width, height), "#101828")
    panel_width = width // 3
    for index, item in enumerate(selected):
        poster = download_poster(item["poster_path"])
        panel = ImageOps.fit(poster, (panel_width + 4, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))
        panel = ImageEnhance.Brightness(panel).enhance(0.72)
        canvas.paste(panel, (index * panel_width, 0))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 45))
    draw.rectangle((0, height - 210, width, height), fill=(0, 0, 0, 165))
    draw.text((60, height - 155), "DOUBAN HOT CHINESE TV", fill="white", font=get_font(48))
    draw.text((64, height - 92), now.strftime("%Y-%m-%d"), fill=(220, 230, 255), font=get_font(30))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    canvas.save(COVER_PATH, format="JPEG", quality=92, optimize=True, progressive=True)


def main():
    config = load_json(CONFIG_PATH, {})
    manual = load_json(MAPPING_PATH, {})
    cache = load_json(CACHE_PATH, {})
    limit = int(config.get("douban_limit", 50))
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    headers = tmdb_headers()

    # 多取 10 条候选：少数豆瓣条目可能尚未收录到 TMDB，跳过后仍保持 50 部可识别剧集。
    subjects = fetch_douban_top(limit + 10)
    resolved = []
    unresolved = []
    for subject in subjects:
        match = resolve_tmdb(subject, headers, manual, cache)
        if not match:
            unresolved.append(subject)
            continue
        if not match.get("poster_path"):
            details = requests.get(f"{TMDB_TV_URL}/{match['id']}", params={"language": "zh-CN"}, headers=headers, timeout=30)
            details.raise_for_status()
            match["poster_path"] = details.json().get("poster_path")
        if not match.get("poster_path"):
            unresolved.append(subject)
            continue
        resolved.append({**subject, "tmdb_id": match["id"], "tmdb_name": match.get("name", subject["title"]), "poster_path": match["poster_path"]})

    if len(resolved) != limit:
        unresolved_path = DATA_DIR / "unresolved.json"
        unresolved_path.write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError(f"前 {limit + 10} 条豆瓣候选中只有 {len(resolved)} 部能匹配 TMDB，无法凑够 {limit} 部")

    if unresolved:
        (DATA_DIR / "unresolved.json").write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    resolved = resolved[:limit]

    selected = random.SystemRandom().sample(resolved, 3)
    make_cover(selected, now)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    base = config["site_base_url"].rstrip("/")
    watch = {
        "name": "豆瓣实时热门华语电视剧 Top 50",
        "cover": f"{base}/cover.jpg?v={now.strftime('%Y%m%d%H%M')}",
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "videos": [
            {"tmdb_id": item["tmdb_id"], "tmdb_type": "tv", "title": item["title"], "sort": item["douban_rank"]}
            for item in resolved
        ],
    }
    WATCH_PATH.write_text(json.dumps(watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成 {len(resolved)} 部；封面随机选择：{', '.join(item['title'] for item in selected)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

