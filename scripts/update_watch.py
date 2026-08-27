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

DOUBAN_TV_URL = "https://m.douban.com/rexxar/api/v2/subject/recent_hot/tv"
DOUBAN_SEARCH_URL = "https://movie.douban.com/j/search_subjects"
DOUBAN_DETAIL_URL = "https://m.douban.com/rexxar/api/v2/subject/{subject_id}"
TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Referer": "https://m.douban.com/tv/",
}
MAINLAND = "中国大陆"


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
    year = subject.get("year")
    if str(year).isdigit():
        return int(year)
    match = re.search(r"(\d{4})", subject.get("card_subtitle", ""))
    return int(match.group(1)) if match else None


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None) -> dict:
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def item_to_subject(item: dict, category: str, tmdb_type: str, rank: int) -> dict:
    return {
        "douban_id": str(item["id"]),
        "title": item["title"],
        "year": get_year(item),
        "douban_rank": rank,
        "category": category,
        "tmdb_type": tmdb_type,
        "douban_url": f"https://movie.douban.com/subject/{item['id']}/",
    }


def fetch_tv_subjects(limit: int) -> list[dict]:
    payload = get_json(
        DOUBAN_TV_URL,
        params={"start": 0, "limit": max(50, limit + 30), "category": "热门", "type": "tv_domestic"},
        headers=HEADERS,
    )
    subjects = []
    for rank, item in enumerate(payload.get("items", []), start=1):
        subtitle = item.get("card_subtitle", "")
        if item.get("type") == "tv" and MAINLAND in subtitle:
            subjects.append(item_to_subject(item, "电视剧", "tv", rank))
    return subjects


def fetch_search_subjects(tag: str, page_limit: int = 50) -> list[dict]:
    subjects = []
    for page_start in range(0, 100, page_limit):
        payload = get_json(
            DOUBAN_SEARCH_URL,
            params={
                "type": "movie",
                "tag": tag,
                "sort": "recommend",
                "page_limit": page_limit,
                "page_start": page_start,
            },
            headers=HEADERS,
        )
        page = payload.get("subjects", [])
        subjects.extend(page)
        if len(page) < page_limit:
            break
    return subjects


def fetch_douban_detail(subject_id: str, detail_cache: dict) -> dict:
    if subject_id not in detail_cache:
        detail_cache[subject_id] = get_json(
            DOUBAN_DETAIL_URL.format(subject_id=subject_id), headers=HEADERS
        )
    return detail_cache[subject_id]


def is_mainland(detail: dict) -> bool:
    return MAINLAND in (detail.get("countries") or [])


def is_japanese(detail: dict) -> bool:
    return "日本" in (detail.get("countries") or [])


def is_animation(detail: dict) -> bool:
    return "动画" in (detail.get("genres") or [])


def fetch_movie_subjects(limit: int, detail_cache: dict) -> list[dict]:
    subjects = []
    for rank, item in enumerate(fetch_search_subjects("热门"), start=1):
        detail = fetch_douban_detail(str(item["id"]), detail_cache)
        if is_mainland(detail) and not is_animation(detail):
            subject = item_to_subject(item, "电影", "movie", rank)
            subject["year"] = detail.get("year")
            subjects.append(subject)
            if len(subjects) >= limit + 10:
                break
    return subjects


def fetch_animation_subjects(limit: int, detail_cache: dict) -> list[dict]:
    mainland_subjects = []
    japanese_subjects = []
    seen = set()

    # The current mainland animation-TV ranking often has fewer than 20 items,
    # so supplement it with the current popular animation movie ranking.
    tv_payload = get_json(
        DOUBAN_TV_URL,
        params={"start": 0, "limit": 100, "category": "热门", "type": "tv_animation"},
        headers=HEADERS,
    )
    for rank, item in enumerate(tv_payload.get("items", []), start=1):
        subject_id = str(item["id"])
        detail = fetch_douban_detail(subject_id, detail_cache)
        if subject_id not in seen and is_animation(detail) and (is_mainland(detail) or is_japanese(detail)):
            subject = item_to_subject(item, "国漫", "tv", rank)
            subject["year"] = detail.get("year")
            if is_mainland(detail):
                mainland_subjects.append(subject)
            else:
                japanese_subjects.append(subject)
            seen.add(subject_id)

    if len(mainland_subjects) + len(japanese_subjects) >= limit:
        return mainland_subjects + japanese_subjects

    for rank, item in enumerate(fetch_search_subjects("动画"), start=1):
        subject_id = str(item["id"])
        if subject_id in seen:
            continue
        detail = fetch_douban_detail(subject_id, detail_cache)
        if is_animation(detail) and (is_mainland(detail) or is_japanese(detail)):
            subject = item_to_subject(item, "国漫", "movie", rank)
            subject["year"] = detail.get("year")
            if is_mainland(detail):
                mainland_subjects.append(subject)
            else:
                japanese_subjects.append(subject)
            seen.add(subject_id)
            if len(mainland_subjects) + len(japanese_subjects) >= limit + 10:
                break

    # Mainland animation comes first. Japanese animation is only a fallback
    # when the mainland candidates cannot fill the requested 20 positions.
    return mainland_subjects + japanese_subjects


def tmdb_headers() -> dict:
    token = os.environ.get("TMDB_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 GitHub Actions Secret: TMDB_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def tmdb_title(result: dict, tmdb_type: str) -> str:
    return result.get("name" if tmdb_type == "tv" else "title", "")


def tmdb_date(result: dict, tmdb_type: str) -> str:
    return result.get("first_air_date" if tmdb_type == "tv" else "release_date", "")


def choose_tmdb_result(subject: dict, results: list[dict]) -> dict | None:
    if not results:
        return None
    source_title = normalize_title(subject["title"])
    source_year = subject.get("year")
    tmdb_type = subject["tmdb_type"]

    def score(result: dict) -> tuple[int, float]:
        candidate_title = normalize_title(tmdb_title(result, tmdb_type))
        candidate_year = tmdb_date(result, tmdb_type)[:4]
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

    return max(results, key=score)


def manual_tmdb_id(value) -> int:
    if isinstance(value, dict):
        value = value.get("tmdb_id")
    return int(value)


def resolve_tmdb(subject: dict, headers: dict, manual: dict, cache: dict) -> dict | None:
    douban_id = subject["douban_id"]
    tmdb_type = subject["tmdb_type"]
    cache_key = f"{tmdb_type}:{douban_id}"
    detail_url = f"{TMDB_API_BASE}/{tmdb_type}"

    if douban_id in manual:
        tmdb_id = manual_tmdb_id(manual[douban_id])
        data = get_json(f"{detail_url}/{tmdb_id}", params={"language": "zh-CN"}, headers=headers)
        return {
            "id": int(data["id"]),
            "name": tmdb_title(data, tmdb_type) or subject["title"],
            "poster_path": data.get("poster_path"),
        }
    if cache_key in cache:
        return cache[cache_key]

    search_path = "search/tv" if tmdb_type == "tv" else "search/movie"
    params = {"query": subject["title"], "language": "zh-CN", "include_adult": "false", "page": 1}
    year_key = "first_air_date_year" if tmdb_type == "tv" else "year"
    if subject.get("year"):
        params[year_key] = subject["year"]
    result = choose_tmdb_result(
        subject,
        get_json(f"{TMDB_API_BASE}/{search_path}", params=params, headers=headers).get("results", []),
    )

    if not result and year_key in params:
        params.pop(year_key)
        result = choose_tmdb_result(
            subject,
            get_json(f"{TMDB_API_BASE}/{search_path}", params=params, headers=headers).get("results", []),
        )
    if not result:
        return None

    data = get_json(f"{detail_url}/{result['id']}", params={"language": "zh-CN"}, headers=headers)
    resolved = {
        "id": int(data["id"]),
        "name": tmdb_title(data, tmdb_type) or subject["title"],
        "poster_path": data.get("poster_path"),
    }
    cache[cache_key] = resolved
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
        panel = ImageOps.fit(
            poster,
            (panel_width + 4, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.42),
        )
        panel = ImageEnhance.Brightness(panel).enhance(0.72)
        canvas.paste(panel, (index * panel_width, 0))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 45))
    draw.rectangle((0, height - 210, width, height), fill=(0, 0, 0, 165))
    draw.text((60, height - 155), "豆瓣实时热门大陆影视 / 国漫", fill="white", font=get_font(48))
    draw.text((64, height - 92), now.strftime("%Y-%m-%d"), fill=(220, 230, 255), font=get_font(30))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    canvas.save(COVER_PATH, format="JPEG", quality=92, optimize=True, progressive=True)


def resolve_category(subjects: list[dict], target: int, headers: dict, manual: dict, cache: dict):
    resolved = []
    unresolved = []
    for subject in subjects:
        match = resolve_tmdb(subject, headers, manual, cache)
        if not match:
            unresolved.append(subject)
            continue
        resolved.append(
            {
                **subject,
                "tmdb_id": match["id"],
                "tmdb_name": match.get("name", subject["title"]),
                "poster_path": match.get("poster_path"),
            }
        )
        if len(resolved) >= target:
            break
    return resolved, unresolved


def main():
    config = load_json(CONFIG_PATH, {})
    manual = load_json(MAPPING_PATH, {})
    cache = load_json(CACHE_PATH, {})
    tv_limit = int(config.get("tv_limit", 20))
    movie_limit = int(config.get("movie_limit", 10))
    animation_limit = int(config.get("animation_limit", 20))
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    headers = tmdb_headers()
    detail_cache = {}

    categories = [
        ("电视剧", tv_limit, fetch_tv_subjects(tv_limit)),
        ("电影", movie_limit, fetch_movie_subjects(movie_limit, detail_cache)),
        ("国漫", animation_limit, fetch_animation_subjects(animation_limit, detail_cache)),
    ]
    all_resolved = []
    all_unresolved = []
    for category, target, subjects in categories:
        resolved, unresolved = resolve_category(subjects, target, headers, manual, cache)
        if len(resolved) < target:
            all_unresolved.extend({**item, "category": category} for item in unresolved)
            all_unresolved.append({"category": category, "required": target, "resolved": len(resolved)})
            continue
        all_resolved.extend(resolved[:target])
        all_unresolved.extend({**item, "category": category} for item in unresolved)

    if len(all_resolved) != tv_limit + movie_limit + animation_limit:
        unresolved_path = DATA_DIR / "unresolved.json"
        unresolved_path.write_text(json.dumps(all_unresolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError(
            f"TMDB 匹配不足：需要 {tv_limit}+{movie_limit}+{animation_limit} 部，实际得到 {len(all_resolved)} 部"
        )

    cover_candidates = [item for item in all_resolved if item.get("poster_path")]
    if len(cover_candidates) < 3:
        raise RuntimeError("TMDB 可用海报少于 3 张，无法生成静态封面")
    selected = random.SystemRandom().sample(cover_candidates, 3)
    make_cover(selected, now)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    base = config["site_base_url"].rstrip("/")
    watch = {
        "name": "豆瓣实时热门大陆电视剧20 + 电影10 + 国漫20",
        "cover": f"{base}/cover.jpg?v={now.strftime('%Y%m%d%H%M')}",
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "videos": [
            {
                "tmdb_id": item["tmdb_id"],
                "tmdb_type": item["tmdb_type"],
                "title": item["title"],
                "sort": position,
            }
            for position, item in enumerate(all_resolved, start=1)
        ],
    }
    WATCH_PATH.write_text(json.dumps(watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成 {len(all_resolved)} 部；封面随机选择：{', '.join(item['title'] for item in selected)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

