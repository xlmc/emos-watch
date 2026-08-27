from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
MAPPING_PATH = ROOT / "mapping.json"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
CACHE_PATH = DATA_DIR / "mapping-cache.json"
SELECTION_PATH = DATA_DIR / "cover-selection.json"
JAPAN_SELECTION_PATH = DATA_DIR / "cover-japan-selection.json"
WATCH_PATH = ROOT / "watch.json"
JAPAN_WATCH_PATH = ROOT / "watch-japan.json"
COVER_PATH = ROOT / "cover.gif"
JAPAN_COVER_PATH = ROOT / "cover-japan.gif"

DOUBAN_TV_URL = "https://m.douban.com/rexxar/api/v2/subject/recent_hot/tv"
DOUBAN_SEARCH_URL = "https://movie.douban.com/j/search_subjects"
DOUBAN_DETAIL_URL = "https://m.douban.com/rexxar/api/v2/subject/{subject_id}"
TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"
BGM_API_BASE = "https://api.bgm.tv/v0"
ANILIST_API_URL = "https://graphql.anilist.co"
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
    last_error = None
    for attempt in range(4):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_error


def post_json(
    url: str,
    payload: dict,
    *,
    params: dict | None = None,
    headers: dict | None = None,
) -> dict:
    last_error = None
    for attempt in range(4):
        try:
            response = requests.post(url, params=params, json=payload, headers=headers, timeout=30)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_error


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


def fetch_douban_details(subject_ids: list[str], detail_cache: dict):
    pending = list(dict.fromkeys(subject_id for subject_id in subject_ids if subject_id not in detail_cache))
    if not pending:
        return
    # 豆瓣详情接口对并发和短时间重复请求较敏感，降低并发并配合 get_json 重试。
    with ThreadPoolExecutor(max_workers=4) as executor:
        details = list(executor.map(lambda subject_id: get_json(
            DOUBAN_DETAIL_URL.format(subject_id=subject_id), headers=HEADERS
        ), pending))
    detail_cache.update(dict(zip(pending, details)))


def is_mainland(detail: dict) -> bool:
    return MAINLAND in (detail.get("countries") or [])


def is_japanese(detail: dict) -> bool:
    return "日本" in (detail.get("countries") or [])


def is_animation(detail: dict) -> bool:
    return "动画" in (detail.get("genres") or [])


def fetch_movie_subjects(limit: int, detail_cache: dict) -> list[dict]:
    subjects = []
    items = fetch_search_subjects("热门")
    fetch_douban_details([str(item["id"]) for item in items], detail_cache)
    for rank, item in enumerate(items, start=1):
        detail = detail_cache[str(item["id"])]
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
    fetch_douban_details([str(item["id"]) for item in tv_payload.get("items", [])], detail_cache)
    for rank, item in enumerate(tv_payload.get("items", []), start=1):
        subject_id = str(item["id"])
        detail = detail_cache[subject_id]
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

    animation_items = fetch_search_subjects("动画")
    fetch_douban_details([str(item["id"]) for item in animation_items], detail_cache)
    for rank, item in enumerate(animation_items, start=1):
        subject_id = str(item["id"])
        if subject_id in seen:
            continue
        detail = detail_cache[subject_id]
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


def download_poster(poster_path: str) -> Image.Image:
    url = f"{TMDB_IMAGE_BASE}{poster_path}"
    for attempt in range(4):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB")
        except (requests.RequestException, OSError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"TMDB 海报下载失败：{url}")


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def make_triptych(posters: list[Image.Image], size: tuple[int, int]) -> Image.Image:
    width, height = size
    result = Image.new("RGB", size)
    cuts = [0, width // 3, width * 2 // 3, width]
    for index, poster in enumerate(posters):
        panel_width = cuts[index + 1] - cuts[index]
        panel = ImageOps.fit(
            poster,
            (panel_width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.38),
        )
        result.paste(panel, (cuts[index], 0))
    return result


def add_glass_layer(canvas: Image.Image, source: Image.Image, angle: float, tint: tuple[int, int, int]):
    layer_size = (720, 392)
    glass = ImageOps.fit(source, layer_size, method=Image.Resampling.LANCZOS)
    glass = glass.filter(ImageFilter.GaussianBlur(18)).convert("RGBA")
    glass = Image.blend(glass, Image.new("RGBA", layer_size, (*tint, 255)), 0.38)
    glass.putalpha(rounded_mask(layer_size, 54).point(lambda value: value * 150 // 255))

    rim = Image.new("RGBA", layer_size, (0, 0, 0, 0))
    rim_draw = ImageDraw.Draw(rim)
    rim_draw.rounded_rectangle(
        (3, 3, layer_size[0] - 4, layer_size[1] - 4),
        52,
        outline=(*tint, 180),
        width=4,
    )
    rim_draw.line((72, 4, 286, 4), fill=(255, 255, 255, 145), width=3)
    glass = Image.alpha_composite(glass, rim)
    glass = glass.rotate(angle, Image.Resampling.BICUBIC, expand=True)

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    box = (
        (canvas.width - glass.width) // 2 - 14,
        (canvas.height - glass.height) // 2 - 14,
        (canvas.width + glass.width) // 2 + 14,
        (canvas.height + glass.height) // 2 + 14,
    )
    glow_draw.rounded_rectangle(box, 70, outline=(*tint, 125), width=18)
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    canvas.alpha_composite(glow)
    canvas.alpha_composite(glass, ((canvas.width - glass.width) // 2, (canvas.height - glass.height) // 2))


def build_cover_base(posters: list[Image.Image]) -> Image.Image:
    width, height = 960, 528
    collage = make_triptych(posters, (width, height))
    background = ImageEnhance.Color(collage).enhance(0.72)
    background = ImageEnhance.Brightness(background).enhance(0.72)
    background = background.filter(ImageFilter.GaussianBlur(24))

    # 让模糊海报铺满整个画布；只加轻微深蓝遮罩，不使用纯黑外框。
    canvas = background.convert("RGBA")
    canvas = Image.alpha_composite(canvas, Image.new("RGBA", (width, height), (7, 20, 43, 28)))
    stage_size = (936, 504)
    stage = ImageOps.fit(background, stage_size, method=Image.Resampling.LANCZOS).convert("RGBA")
    stage.putalpha(rounded_mask(stage_size, 38))
    canvas.alpha_composite(stage, (12, 12))

    shade = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    shade_draw.rounded_rectangle((12, 12, 947, 515), 38, fill=(0, 5, 12, 45), outline=(255, 255, 255, 42), width=2)
    canvas = Image.alpha_composite(canvas, shade)

    add_glass_layer(canvas, collage, -7.5, (114, 87, 210))
    add_glass_layer(canvas, collage, 6.5, (49, 139, 242))

    card_size = (672, 378)
    card = make_triptych(posters, card_size).convert("RGBA")
    card.putalpha(rounded_mask(card_size, 34))
    card_x = (width - card_size[0]) // 2
    card_y = (height - card_size[1]) // 2

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (card_x - 8, card_y + 10, card_x + card_size[0] + 8, card_y + card_size[1] + 24),
        42,
        fill=(0, 0, 0, 185),
    )
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    canvas.alpha_composite(card, (card_x, card_y))

    rim = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    rim_draw = ImageDraw.Draw(rim)
    rim_draw.rounded_rectangle(
        (card_x, card_y, card_x + card_size[0] - 1, card_y + card_size[1] - 1),
        34,
        outline=(159, 215, 255, 155),
        width=3,
    )
    rim_draw.line(
        (card_x + 48, card_y + 2, card_x + 268, card_y + 2),
        fill=(255, 255, 255, 185),
        width=3,
    )
    canvas = Image.alpha_composite(canvas, rim)
    return canvas.convert("RGB")


def ripple_frame(base: Image.Image, frame_index: int, frame_count: int) -> Image.Image:
    width, height = base.size
    progress = frame_index / frame_count
    band = -260 + progress * (width + 520)
    phase = progress * 6.283185307
    step = 32
    mesh = []

    def displacement(x: int, y: int) -> float:
        diagonal_x = x + y * 0.38
        envelope = pow(2.718281828, -((diagonal_x - band) / 150) ** 2)
        return 5.5 * envelope * __import__("math").sin(y / 13.0 + phase)

    for top in range(0, height, step):
        bottom = min(top + step, height)
        for left in range(0, width, step):
            right = min(left + step, width)
            quad = (
                max(0, min(width - 1, left + displacement(left, top))), top,
                max(0, min(width - 1, left + displacement(left, bottom))), bottom,
                max(0, min(width - 1, right + displacement(right, bottom))), bottom,
                max(0, min(width - 1, right + displacement(right, top))), top,
            )
            mesh.append(((left, top, right, bottom), quad))

    warped = base.transform(base.size, Image.Transform.MESH, mesh, Image.Resampling.BICUBIC).convert("RGBA")
    sheen = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheen)
    x = band - height * 0.38
    draw.polygon(
        [(x - 95, 0), (x + 15, 0), (x + 15 + height * 0.38, height), (x - 95 + height * 0.38, height)],
        fill=(210, 242, 255, 55),
    )
    draw.line((x, 0, x + height * 0.38, height), fill=(255, 255, 255, 120), width=4)
    sheen = sheen.filter(ImageFilter.GaussianBlur(18))
    return Image.alpha_composite(warped, sheen).convert("RGB")


def make_cover(selected: list[dict], now: datetime, output_path: Path):
    posters = [download_poster(item["poster_path"]) for item in selected]
    base = build_cover_base(posters)
    frame_count = 18
    frames = [ripple_frame(base, index, frame_count) for index in range(frame_count)]
    palette = frames[0].convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    gif_frames = [palette]
    gif_frames.extend(frame.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG) for frame in frames[1:])
    gif_frames[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=gif_frames[1:],
        duration=200,
        loop=0,
        optimize=True,
        disposal=2,
    )


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


def fetch_tmdb_japanese_anime(headers: dict, now: datetime, limit: int = 50) -> list[dict]:
    """从 TMDB 获取今年以来已上线的日本动画电视剧，按首播日期倒序。"""
    start_date = f"{now.year}-01-01"
    end_date = now.strftime("%Y-%m-%d")
    results = []
    seen = set()

    for page in range(1, 11):
        payload = get_json(
            f"{TMDB_API_BASE}/discover/tv",
            params={
                "language": "zh-CN",
                "sort_by": "first_air_date.desc",
                "first_air_date.gte": start_date,
                "first_air_date.lte": end_date,
                "with_origin_country": "JP",
                "with_original_language": "ja",
                "with_genres": "16",
                "include_null_first_air_dates": "false",
                "page": page,
            },
            headers=headers,
        )
        for item in payload.get("results", []):
            tmdb_id = int(item["id"])
            first_air_date = item.get("first_air_date", "")
            if tmdb_id in seen or not first_air_date:
                continue
            seen.add(tmdb_id)
            results.append(
                {
                    "tmdb_id": tmdb_id,
                    "tmdb_type": "tv",
                    "title": item.get("name") or item.get("original_name") or f"TMDB {tmdb_id}",
                    "first_air_date": first_air_date,
                    "poster_path": item.get("poster_path"),
                }
            )
            if len(results) >= limit:
                break
        if len(results) >= limit or page >= int(payload.get("total_pages", page)):
            break

    results.sort(key=lambda item: (item["first_air_date"], item["tmdb_id"]), reverse=True)
    return results[:limit]


def fetch_bangumi_anime(now: datetime, limit: int = 100) -> list[dict]:
    """从 Bangumi 获取今年日本 TV 动画，日期稍后与 TMDB/AniList 合并。"""
    items = []
    try:
        for offset in range(0, 200, 50):
            payload = post_json(
                f"{BGM_API_BASE}/search/subjects",
                {
                    "keyword": "",
                    "sort": "heat",
                    "filter": {
                        "type": [2],
                        "tag": ["日本", "TV"],
                        "air_date": [f">={now.year}-01-01", f"<={now.strftime('%Y-%m-%d')}"],
                        "nsfw": False,
                    },
                },
                params={"limit": 50, "offset": offset},
                headers={"User-Agent": "emos-watch/1.0 (https://github.com/xlmc/emos-watch)"},
            )
            page = payload.get("data", [])
            for item in page:
                if item.get("type") != 2 or not item.get("date"):
                    continue
                items.append(
                    {
                        "source": "bgm",
                        "title": item.get("name_cn") or item.get("name"),
                        "search_titles": [item.get("name_cn"), item.get("name")],
                        "first_air_date": item["date"],
                    }
                )
            if len(page) < 50 or offset + len(page) >= int(payload.get("total", 0)) or len(items) >= limit:
                break
    except Exception as exc:
        print(f"警告：Bangumi 获取失败，继续使用其他日番源：{exc}")
        return []
    return sorted(items, key=lambda item: item["first_air_date"], reverse=True)[:limit]


ANILIST_QUERY = """
query ($page: Int, $perPage: Int, $from: FuzzyDateInt, $until: FuzzyDateInt) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(
      type: ANIME,
      countryOfOrigin: JP,
      startDate_greater: $from,
      startDate_lesser: $until,
      format_in: [TV, TV_SHORT, ONA],
      sort: START_DATE_DESC
    ) {
      id
      title { romaji english native }
      startDate { year month day }
    }
  }
}
"""


def fetch_anilist_anime(now: datetime, limit: int = 100) -> list[dict]:
    """从 AniList 获取今年日本 TV/短番/ONA，日期稍后与其他源合并。"""
    items = []
    try:
        payload = post_json(
            ANILIST_API_URL,
            {
                "query": ANILIST_QUERY,
                "variables": {
                    "page": 1,
                    "perPage": min(limit, 50),
                    "from": int(f"{now.year - 1}1231"),
                    "until": int((now.date() + timedelta(days=1)).strftime("%Y%m%d")),
                },
            },
            headers={"Content-Type": "application/json", "User-Agent": "emos-watch/1.0"},
        )
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        for item in payload.get("data", {}).get("Page", {}).get("media", []):
            date = item.get("startDate") or {}
            if not date.get("year") or not date.get("month") or not date.get("day"):
                continue
            title = item.get("title") or {}
            items.append(
                {
                    "source": "anilist",
                    "title": title.get("romaji") or title.get("native") or title.get("english"),
                    "search_titles": [title.get("romaji"), title.get("native"), title.get("english")],
                    "first_air_date": f"{date['year']:04d}-{date['month']:02d}-{date['day']:02d}",
                }
            )
    except Exception as exc:
        print(f"警告：AniList 获取失败，继续使用其他日番源：{exc}")
        return []
    return sorted(items, key=lambda item: item["first_air_date"], reverse=True)[:limit]


def resolve_external_tv_to_tmdb(item: dict, headers: dict) -> dict | None:
    year = int(item["first_air_date"][:4])
    subject = {"title": item["title"], "year": year, "tmdb_type": "tv"}
    for title in dict.fromkeys(value for value in item.get("search_titles", []) if value):
        params = {
            "query": title,
            "language": "zh-CN",
            "include_adult": "false",
            "first_air_date_year": year,
            "page": 1,
        }
        result = choose_tmdb_result(
            {**subject, "title": title},
            get_json(f"{TMDB_API_BASE}/search/tv", params=params, headers=headers).get("results", []),
        )
        if not result:
            continue
        data = get_json(f"{TMDB_API_BASE}/tv/{result['id']}", params={"language": "zh-CN"}, headers=headers)
        if "JP" not in (data.get("origin_country") or []) and data.get("original_language") != "ja":
            continue
        return {
            "tmdb_id": int(data["id"]),
            "tmdb_type": "tv",
            "title": data.get("name") or item["title"],
            "first_air_date": data.get("first_air_date") or item["first_air_date"],
            "poster_path": data.get("poster_path"),
        }
    return None


def fetch_japanese_anime(headers: dict, now: datetime, limit: int = 50) -> list[dict]:
    """联合 TMDB、Bangumi、AniList，按首播时间倒序合并并统一为 TMDB ID。"""
    tmdb_items = fetch_tmdb_japanese_anime(headers, now, limit)
    merged = {item["tmdb_id"]: item for item in tmdb_items}
    known_titles = {normalize_title(item["title"]) for item in merged.values()}

    external_items = fetch_bangumi_anime(now, 100) + fetch_anilist_anime(now, 100)
    external_items.sort(key=lambda item: item["first_air_date"], reverse=True)
    for item in external_items:
        aliases = {normalize_title(value) for value in item.get("search_titles", []) if value}
        if aliases & known_titles:
            continue
        if len(merged) >= limit:
            break
        resolved = resolve_external_tv_to_tmdb(item, headers)
        if not resolved or resolved["tmdb_id"] in merged:
            continue
        merged[resolved["tmdb_id"]] = resolved
        known_titles.add(normalize_title(resolved["title"]))

    return sorted(merged.values(), key=lambda item: (item["first_air_date"], item["tmdb_id"]), reverse=True)[:limit]


VARIETY_PLATFORM_KEYWORDS = (
    "优酷", "youku", "腾讯", "tencent", "芒果", "mango", "爱奇艺", "iqiyi", "iQIYI"
)


def fetch_chinese_variety(headers: dict, now: datetime, limit: int = 50) -> list[dict]:
    """从 TMDB 筛选国内综艺：指定平台、仍在制作/连载且近期或即将播出。"""
    today = now.date()
    recent_date = (today - timedelta(days=120)).isoformat()
    future_date = (today + timedelta(days=30)).isoformat()
    discovered = {}

    for page in range(1, 11):
        payload = get_json(
            f"{TMDB_API_BASE}/discover/tv",
            params={
                "language": "zh-CN",
                "sort_by": "popularity.desc",
                "air_date.gte": recent_date,
                "air_date.lte": future_date,
                "with_origin_country": "CN",
                "with_genres": "10764",
                "include_null_first_air_dates": "false",
                "page": page,
            },
            headers=headers,
        )
        for item in payload.get("results", []):
            discovered[int(item["id"])] = item
        if page >= int(payload.get("total_pages", page)):
            break

    results = []
    for item in sorted(discovered.values(), key=lambda value: float(value.get("popularity") or 0), reverse=True):
        data = get_json(
            f"{TMDB_API_BASE}/tv/{item['id']}",
            params={"language": "zh-CN", "append_to_response": "watch/providers"},
            headers=headers,
        )
        network_names = [network.get("name", "") for network in data.get("networks", [])]
        provider_names = []
        cn_providers = (data.get("watch/providers") or {}).get("results", {}).get("CN", {})
        for group in ("flatrate", "free", "ads", "rent", "buy"):
            provider_names.extend(provider.get("provider_name", "") for provider in cn_providers.get(group, []))
        platform_names = network_names + provider_names
        if not any(
            keyword.lower() in name.lower()
            for name in platform_names
            for keyword in VARIETY_PLATFORM_KEYWORDS
        ):
            continue

        last_air = (data.get("last_episode_to_air") or {}).get("air_date") or data.get("last_air_date") or ""
        next_air = (data.get("next_episode_to_air") or {}).get("air_date") or ""
        last_is_recent = bool(last_air and last_air >= recent_date)
        next_is_near = bool(next_air and next_air <= future_date)
        active_status = data.get("status") in {"Returning Series", "In Production", "Pilot"}
        if not active_status or not (last_is_recent or next_is_near or data.get("in_production")):
            continue
        results.append(
            {
                "tmdb_id": int(data["id"]),
                "tmdb_type": "tv",
                "title": data.get("name") or item.get("name") or f"TMDB {data['id']}",
                "first_air_date": data.get("first_air_date") or "",
                "last_air_date": last_air,
                "next_air_date": next_air,
                "popularity": float(data.get("popularity") or item.get("popularity") or 0),
                "poster_path": data.get("poster_path") or item.get("poster_path"),
            }
        )
        if len(results) >= limit:
            break

    results.sort(key=lambda item: (item["popularity"], item["last_air_date"], item["next_air_date"]), reverse=True)
    return results[:limit]


def select_daily_cover(candidates: list[dict], now: datetime, selection_path: Path) -> list[dict]:
    candidates = sorted(candidates, key=lambda item: (item["tmdb_type"], item["tmdb_id"]))
    candidate_map = {(item["tmdb_type"], item["tmdb_id"]): item for item in candidates}
    selection_state = load_json(selection_path, {})
    saved_keys = [tuple(value) for value in selection_state.get("items", [])]
    if (
        selection_state.get("date") == now.strftime("%Y-%m-%d")
        and len(saved_keys) == 3
        and all(key in candidate_map for key in saved_keys)
    ):
        return [candidate_map[key] for key in saved_keys]

    selected = random.SystemRandom().sample(candidates, 3)
    selection_path.write_text(
        json.dumps(
            {
                "date": now.strftime("%Y-%m-%d"),
                "items": [[item["tmdb_type"], item["tmdb_id"]] for item in selected],
                "titles": [item["title"] for item in selected],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return selected


def main():
    config = load_json(CONFIG_PATH, {})
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    headers = tmdb_headers()
    base = config["site_base_url"].rstrip("/")

    japan_items = fetch_japanese_anime(headers, now, limit=50)
    japan_cover_candidates = [item for item in japan_items if item.get("poster_path")]
    if len(japan_cover_candidates) < 3:
        raise RuntimeError(f"今年以来 TMDB/Bangumi/AniList 日番海报不足 3 张，当前仅有 {len(japan_cover_candidates)} 张")
    japan_selected = select_daily_cover(japan_cover_candidates, now, JAPAN_SELECTION_PATH)
    make_cover(japan_selected, now, JAPAN_COVER_PATH)
    japan_watch = {
        "name": f"今年最新日番（{len(japan_items)}部）",
        "cover": f"{base}/cover-japan.gif",
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "videos": [
            {
                "tmdb_id": item["tmdb_id"],
                "tmdb_type": item["tmdb_type"],
                "title": item["title"],
                "sort": position,
            }
            for position, item in enumerate(japan_items, start=1)
        ],
    }
    JAPAN_WATCH_PATH.write_text(json.dumps(japan_watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    variety_items = fetch_chinese_variety(headers, now, limit=50)
    variety_cover_candidates = [item for item in variety_items if item.get("poster_path")]
    if len(variety_cover_candidates) < 3:
        raise RuntimeError(f"指定平台的在播综艺海报不足 3 张，当前仅有 {len(variety_cover_candidates)} 张")
    variety_selected = select_daily_cover(variety_cover_candidates, now, SELECTION_PATH)
    make_cover(variety_selected, now, COVER_PATH)
    variety_watch = {
        "name": f"国内流媒体热播更新综艺（{len(variety_items)}部）",
        "cover": f"{base}/cover.gif",
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "videos": [
            {
                "tmdb_id": item["tmdb_id"],
                "tmdb_type": item["tmdb_type"],
                "title": item["title"],
                "sort": position,
            }
            for position, item in enumerate(variety_items, start=1)
        ],
    }
    WATCH_PATH.write_text(json.dumps(variety_watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"已生成日番 {len(japan_items)} 部和国内流媒体热播综艺 {len(variety_items)} 部；"
        f"今日封面：{', '.join(item['title'] for item in japan_selected)} / "
        f"{', '.join(item['title'] for item in variety_selected)}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

