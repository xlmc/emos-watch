from __future__ import annotations

import json
import os
import random
import re
import shutil
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
RELEASE_STATE_PATH = DATA_DIR / "release-state.json"
SELECTION_PATH = DATA_DIR / "cover-selection.json"
VARIETY_SELECTION_PATH = DATA_DIR / "cover-variety-selection.json"
JAPAN_SELECTION_PATH = DATA_DIR / "cover-japan-selection.json"
KAMEN_SELECTION_PATH = DATA_DIR / "cover-kamen-rider-selection.json"
SENTAI_SELECTION_PATH = DATA_DIR / "cover-super-sentai-selection.json"
WATCH_PATH = ROOT / "watch.json"
VARIETY_WATCH_PATH = ROOT / "watch-variety.json"
JAPAN_WATCH_PATH = ROOT / "watch-japan.json"
TMDB_MIX_WATCH_PATH = ROOT / "watch-tmdb-mix-v4.json"
TMDB_MIX_V3_WATCH_PATH = ROOT / "watch-tmdb-mix-v3.json"
TMDB_MIX_V2_WATCH_PATH = ROOT / "watch-tmdb-mix-v2.json"
TMDB_MIX_LEGACY_WATCH_PATH = ROOT / "watch-tmdb-mix.json"
KAMEN_WATCH_PATH = ROOT / "watch-kamen-rider.json"
SENTAI_WATCH_PATH = ROOT / "watch-super-sentai.json"
COVER_PATH = ROOT / "cover.gif"
VARIETY_COVER_PATH = ROOT / "cover-variety.gif"
JAPAN_COVER_PATH = ROOT / "cover-japan.gif"
TMDB_MIX_COVER_PATH = ROOT / "cover-tmdb-mix-v4.gif"
TMDB_MIX_V3_COVER_PATH = ROOT / "cover-tmdb-mix-v3.gif"
TMDB_MIX_V2_COVER_PATH = ROOT / "cover-tmdb-mix-v2.gif"
TMDB_MIX_LEGACY_COVER_PATH = ROOT / "cover-tmdb-mix.gif"
KAMEN_COVER_PATH = ROOT / "cover-kamen-rider.gif"
SENTAI_COVER_PATH = ROOT / "cover-super-sentai.gif"

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"
BGM_API_BASE = "https://api.bgm.tv/v0"
ANILIST_API_URL = "https://graphql.anilist.co"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
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

def tmdb_headers() -> dict:
    """构造 TMDB v4 Bearer 鉴权请求头，不把密钥写入仓库。"""
    token = os.environ.get("TMDB_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 TMDB_API_TOKEN，请在 GitHub Actions Secrets 中配置 TMDB Read Access Token。")
    authorization = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return {
        "Authorization": authorization,
        "Accept": "application/json",
        "User-Agent": HEADERS["User-Agent"],
    }

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

def download_poster(poster_path: str, image_url: str | None = None) -> Image.Image:
    url = image_url or f"{TMDB_IMAGE_BASE}{poster_path}"
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
    posters = [download_poster(item["poster_path"], item.get("poster_url")) for item in selected]
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

def previous_month_start(today) -> str:
    first_day = today.replace(day=1)
    return (first_day - timedelta(days=1)).replace(day=1).isoformat()

def fetch_tmdb_discover(
    path: str,
    headers: dict,
    params: dict,
    limit: int,
    max_pages: int = 10,
) -> list[dict]:
    """按 TMDB Discover 条件抓取并去重，结果保持 API 的日期排序。"""
    items = []
    seen = set()
    for page in range(1, max_pages + 1):
        payload = get_json(
            f"{TMDB_API_BASE}/discover/{path}",
            params={**params, "page": page},
            headers=headers,
        )
        for item in payload.get("results", []):
            if not item.get("id") or int(item["id"]) in seen:
                continue
            seen.add(int(item["id"]))
            items.append(item)
            if len(items) >= limit:
                return items
        if page >= int(payload.get("total_pages", page)):
            break
    return items

def tmdb_catalog_item(item: dict, tmdb_type: str, category: str) -> dict:
    date_key = "first_air_date" if tmdb_type == "tv" else "release_date"
    title_key = "name" if tmdb_type == "tv" else "title"
    return {
        "tmdb_id": int(item["id"]),
        "tmdb_type": tmdb_type,
        "title": item.get(title_key) or item.get("original_name" if tmdb_type == "tv" else "original_title") or f"TMDB {item['id']}",
        "first_air_date": item.get(date_key) or "",
        "poster_path": item.get("poster_path"),
        "category": category,
    }

def parse_iso_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None

def fetch_tmdb_mainland_tv(
    headers: dict,
    now: datetime,
    state: dict,
    limit: int = 20,
) -> list[dict]:
    """抓取 TMDB 当前仍在更新的大陆长篇电视剧，按首播时间倒序。

    TMDB 的中国大陆条目里会混入微短剧、竖屏剧和游戏/宣传类条目。
    先用质量和长剧条件筛选，再按上线时间输出，避免为了凑满 20 部而混入明显异常内容。
    """
    today = now.date()
    today_text = today.isoformat()
    recent_start_text = (today - timedelta(days=365)).isoformat()
    # 电视剧有时会因为 TMDB 的分集资料延迟而没有在最近几周更新，
    # 适当放宽检测窗口，但仍要求状态为正在制作/连载。
    recent_text = (today - timedelta(days=180)).isoformat()
    future_text = (today + timedelta(days=30)).isoformat()
    discovered = fetch_tmdb_discover(
        "tv",
        headers,
        {
            "language": "zh-CN",
            # 先从较成熟、热度更高的条目中挑选候选；最终输出仍按首播日期倒序。
            "sort_by": "popularity.desc",
            "first_air_date.lte": today_text,
            "with_origin_country": "CN",
            "without_genres": "16,99,10764,10763,10767,10762",
            "include_null_first_air_dates": "false",
        },
        limit=100,
        max_pages=10,
    )
    finale_state = state.get("tv_finale_dates_v1")
    if not isinstance(finale_state, dict):
        finale_state = {}

    candidates = []
    for item in discovered:
        data = get_json(
            f"{TMDB_API_BASE}/tv/{item['id']}",
            params={"language": "zh-CN"},
            headers=headers,
        )
        first_air_date = data.get("first_air_date") or item.get("first_air_date") or ""
        if not first_air_date or first_air_date > today_text:
            continue
        # 避免把《乡村爱情》这类多年以前开始、但被 TMDB 标为持续制作的老系列
        # 当作“最新上线电视剧”；当前片单只看近一年内上线且仍在更新的剧集。
        if first_air_date < recent_start_text:
            continue
        origin_country = data.get("origin_country") or item.get("origin_country") or []
        if "CN" not in origin_country and data.get("original_language") not in {"zh", "cn"}:
            continue
        if data.get("original_language") not in {"zh", "cn"}:
            continue
        genre_ids = {int(value) for value in (item.get("genre_ids") or []) if str(value).isdigit()}
        genre_ids.update(
            int(genre.get("id"))
            for genre in (data.get("genres") or [])
            if str(genre.get("id", "")).isdigit()
        )
        if genre_ids.intersection({16, 10764, 10763, 10767, 10762}):
            continue
        title_text = " ".join(
            str(data.get(key) or "") for key in ("name", "original_name")
        )
        if any(
            keyword in title_text
            for keyword in (
                "赛事", "自行车赛", "文学经典", "寓言", "警长", "巡逻行动", "玩家", "游戏",
                "微短剧", "短剧", "竖屏", "快穿", "系统", "总裁", "闪婚", "离婚",
                "替身", "千金", "萌宝", "神医", "赘婿", "逆袭", "重生", "契约",
                "霹雳", "布袋戏", "戏曲", "舞台剧", "纪录片", "纪录",
                "中配", "开门大吉", "X调查",
            )
        ):
            continue

        key = f"tv:{data['id']}"
        last_episode = data.get("last_episode_to_air") or {}
        finale_date = ""
        if data.get("status") == "Ended":
            finale_date = last_episode.get("air_date") or data.get("last_air_date") or ""
        if finale_date:
            finale_state[key] = finale_date
        else:
            finale_date = finale_state.get(key, "")
        finale_day = parse_iso_date(finale_date)
        if finale_day and (today - finale_day).days >= 3:
            continue
        last_air_date = last_episode.get("air_date") or data.get("last_air_date") or ""
        next_air_date = (data.get("next_episode_to_air") or {}).get("air_date") or ""
        is_currently_updating = (
            data.get("status") in {"Returning Series", "In Production", "Pilot"}
            and (
                (bool(last_air_date) and last_air_date >= recent_text)
                or (bool(next_air_date) and next_air_date <= future_text)
            )
        )
        is_finale_grace_period = bool(finale_day and (today - finale_day).days < 3)
        if not is_currently_updating and not is_finale_grace_period:
            continue
        run_times = [int(value) for value in (data.get("episode_run_time") or []) if str(value).isdigit()]
        max_runtime = max(run_times, default=0)
        try:
            episode_count = int(data.get("number_of_episodes") or 0)
        except (TypeError, ValueError):
            episode_count = 0
        try:
            vote_count = int(data.get("vote_count") or 0)
        except (TypeError, ValueError):
            vote_count = 0
        popularity = float(data.get("popularity") or item.get("popularity") or 0)
        # 长剧只通过质量分优先，不按集数/片长硬删；《邻人可疑》这类正常短篇
        # 网络剧也可以进入，明显的竖屏微短剧仍由上面的关键词过滤。
        # 新剧可能暂时没有很多票，但不能让完全没有质量信号的条目进入主电视剧区。
        vote_average = float(data.get("vote_average") or 0)
        if vote_count < 3 and popularity < 1.5:
            continue
        if vote_count >= 10 and vote_average and vote_average < 5.0:
            continue

        quality_score = (
            popularity
            + min(float(data.get("vote_average") or 0), 10.0) * 1.5
            + min(vote_count, 500) / 100
            + min(max_runtime, 60) / 20
            + min(episode_count, 60) / 30
        )

        candidates.append(
            {
                **tmdb_catalog_item(data, "tv", "电视剧"),
                "first_air_date": first_air_date,
                "finale_date": finale_date,
                "quality_score": quality_score,
            }
        )

    state["tv_finale_dates_v1"] = finale_state
    # 先取质量更可靠的候选，再按用户要求以首播时间从新到旧排列。
    candidates.sort(key=lambda value: value["quality_score"], reverse=True)
    selected = candidates[: max(limit * 2, limit)]
    return sorted(selected, key=lambda value: (value["first_air_date"], value["tmdb_id"]), reverse=True)[:limit]

def fetch_tmdb_mainland_animation(headers: dict, now: datetime, limit: int = 20) -> list[dict]:
    """抓取正在更新、并按最新上线时间排列的大陆动画 TV。

    只按动画类型和首播日期会把已经结束多年的老番也带进来；这里要求 TMDB
    标记为正在播/连载，并且近期有上一集或即将有下一集。不使用已完结作品凑数。
    """
    current_year_items = fetch_tmdb_discover(
        "tv",
        headers,
        {
            "language": "zh-CN",
            "sort_by": "first_air_date.desc",
            "first_air_date.lte": now.strftime("%Y-%m-%d"),
            "with_origin_country": "CN",
            "with_original_language": "zh",
            "with_genres": "16",
            "without_genres": "99,10764,10767",
            "vote_count.gte": 5,
            "include_null_first_air_dates": "false",
        },
        # discover 结果中可能包含特别篇/合集，先多取候选再过滤，避免国漫无故少于 20 部。
        limit=max(limit * 4, 80),
        max_pages=10,
    )
    active_items = fetch_tmdb_discover(
        "tv",
        headers,
        {
            "language": "zh-CN",
            "sort_by": "popularity.desc",
            "with_origin_country": "CN",
            "with_original_language": "zh",
            "with_genres": "16",
            "without_genres": "99,10764,10767",
            "vote_count.gte": 3,
            "include_null_first_air_dates": "false",
        },
        limit=max(limit * 4, 80),
        max_pages=10,
    )
    items = []
    seen = set()
    for item in current_year_items + active_items:
        tmdb_id = int(item["id"])
        if tmdb_id in seen:
            continue
        seen.add(tmdb_id)
        items.append(item)

    today = now.date()
    recent_episode_cutoff = (today - timedelta(days=120)).isoformat()
    future_episode_limit = (today + timedelta(days=30)).isoformat()
    results = []
    for item in items:
        if not item.get("first_air_date"):
            continue
        data = get_json(
            f"{TMDB_API_BASE}/tv/{item['id']}",
            params={"language": "zh-CN"},
            headers=headers,
        )
        first_air_date = data.get("first_air_date") or item.get("first_air_date") or ""
        if not first_air_date:
            continue
        origin_country = data.get("origin_country") or item.get("origin_country") or []
        if "CN" not in origin_country and data.get("original_language") not in {"zh", "cn"}:
            continue
        if data.get("original_language") not in {"zh", "cn"}:
            continue
        title_text = " ".join(str(item.get(key) or "") for key in ("name", "original_name"))
        if any(
            keyword in title_text
            for keyword in (
                "特别篇", "剧场版", "宣传片", "宣传", "短片", "玩家", "安全警长",
                "摸金", "绘本", "游戏", "怪兽大电影", "黑神话", "章节动画", "原版合集", "合集",
            )
        ):
            continue
        last_air_date = (data.get("last_episode_to_air") or {}).get("air_date") or data.get("last_air_date") or ""
        next_air_date = (data.get("next_episode_to_air") or {}).get("air_date") or ""
        is_currently_updating = (
            data.get("status") in {"Returning Series", "In Production", "Pilot"}
            and (
                (bool(last_air_date) and last_air_date >= recent_episode_cutoff)
                or (bool(next_air_date) and next_air_date <= future_episode_limit)
                or bool(data.get("in_production"))
            )
        )
        if not is_currently_updating:
            continue
        catalog_item = tmdb_catalog_item(
            {**item, **data, "first_air_date": first_air_date},
            "tv",
            "国漫",
        )
        catalog_item["_currently_updating"] = is_currently_updating
        catalog_item["_activity_date"] = last_air_date or next_air_date or first_air_date
        results.append(catalog_item)
    return sorted(
        results,
        key=lambda value: (
            value["_currently_updating"],
            value["first_air_date"],
            value["tmdb_id"],
        ),
        reverse=True,
    )[:limit]

def fetch_tmdb_mainland_movies(headers: dict, now: datetime, limit: int = 5) -> list[dict]:
    """抓取 TMDB 最新大陆非动画电影，按上映时间倒序。"""
    today_text = now.strftime("%Y-%m-%d")
    start_text = previous_month_start(now.date())

    def discover_movies(start_date: str, max_pages: int) -> list[dict]:
        return fetch_tmdb_discover(
            "movie",
            headers,
            {
                "language": "zh-CN",
                "sort_by": "primary_release_date.desc",
                "primary_release_date.gte": start_date,
                "primary_release_date.lte": today_text,
                "with_origin_country": "CN",
                "with_original_language": "zh",
                "without_genres": "16,99,10770",
                "vote_count.gte": 3,
                "include_adult": "false",
            },
            limit=100,
            max_pages=max_pages,
        )

    results = []
    seen = set()
    def collect_movies(discovered: list[dict]):
        for item in discovered:
            tmdb_id = int(item["id"])
            if tmdb_id in seen or len(results) >= limit:
                continue
            seen.add(tmdb_id)
            data = get_json(
                f"{TMDB_API_BASE}/movie/{tmdb_id}",
                params={"language": "zh-CN", "append_to_response": "release_dates"},
                headers=headers,
            )
            release_date = data.get("release_date") or item.get("release_date") or ""
            if not release_date or release_date > today_text:
                continue
            release_date_by_country = {
                country.get("iso_3166_1"): [
                    entry.get("release_date", "")[:10]
                    for entry in (country.get("release_dates") or [])
                    if entry.get("release_date")
                ]
                for country in (data.get("release_dates", {}).get("results") or [])
            }
            cn_release_dates = release_date_by_country.get("CN") or []
            # 只接受 TMDB 明确记录了中国大陆发行日期且已经发行的电影；
            # 没有 CN 发行记录时不使用海外日期替代，避免把未在国内上映的片子带入。
            if not cn_release_dates or min(cn_release_dates) > today_text:
                continue
            # 国内电影按大陆实际发行日期排序，而不是按海外或节展日期排序。
            release_date = min(cn_release_dates)
            if "CN" not in (data.get("origin_country") or item.get("origin_country") or []):
                continue
            if data.get("status") != "Released":
                continue
            if int(data.get("vote_count") or item.get("vote_count") or 0) < 3:
                continue
            if int(data.get("runtime") or 0) < 60:
                continue
            genre_ids = {int(value) for value in (item.get("genre_ids") or []) if str(value).isdigit()}
            genre_ids.update(
                int(genre.get("id"))
                for genre in (data.get("genres") or [])
                if str(genre.get("id", "")).isdigit()
            )
            if genre_ids.intersection({16, 99, 10770}):
                continue
            results.append(
                {
                    **tmdb_catalog_item(data, "movie", "电影"),
                    "first_air_date": release_date,
                }
            )

    # 只取近期上映的长片；不足 5 部时返回实际符合条件的数量，不混入老片或短片。
    collect_movies(discover_movies(start_text, 10))
    return sorted(results, key=lambda value: (value["first_air_date"], value["tmdb_id"]), reverse=True)[:limit]

def mixed_feed_changed(items: list[dict], output_path: Path) -> bool:
    """只要新上线、顺序变化或三天后移除大结局剧集，就刷新混合片单。"""
    previous = load_json(output_path, {})
    previous_keys = [
        f"{video.get('tmdb_type')}:{video.get('tmdb_id')}"
        for video in previous.get("videos", [])
    ]
    current_keys = [f"{item['tmdb_type']}:{item['tmdb_id']}" for item in items]
    return not output_path.exists() or previous_keys != current_keys

def write_tmdb_mixed_feed(
    items: list[dict],
    base: str,
    now: datetime,
    output_path: Path,
    cover_path: Path,
    feed_name: str,
):
    feed = {
        "name": feed_name,
        "cover": f"{base}/{cover_path.name}",
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "videos": [
            {
                "tmdb_id": item["tmdb_id"],
                "tmdb_type": item["tmdb_type"],
                "title": item["title"],
                "sort": position,
            }
            for position, item in enumerate(items, start=1)
        ],
    }
    output_path.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

TMDB_VARIETY_GENRE_IDS = {10764, 10767}
VARIETY_EXCLUDED_EPISODE_TERMS = (
    "特别篇", "番外", "花絮", "加更", "抢先看", "纯享", "训练室", "企划",
    "直播", "彩蛋", "预告", "预览", "幕后", "bonus", "special", "trailer", "preview",
)

# 只维护系列正剧的白名单。通过白名单搜索 TMDB TV，故不会把电影、特别篇、剧场版或
# 同系列衍生剧混入片单；年份同时用于确认 TMDB 返回的是对应一季正剧。
KAMEN_RIDER_SERIES = (
    (2000, "Kamen Rider Kuuga", "仮面ライダークウガ", "假面骑士空我"),
    (2001, "Kamen Rider Agito", "仮面ライダーアギト", "假面骑士亚极陀"),
    (2002, "Kamen Rider Ryuki", "仮面ライダー龍騎", "假面骑士龙骑"),
    (2003, "Kamen Rider 555", "Kamen Rider Faiz", "仮面ライダー555", "假面骑士555"),
    (2004, "Kamen Rider Blade", "仮面ライダーブレイド", "假面骑士剑"),
    (2005, "Kamen Rider Hibiki", "仮面ライダー響鬼", "假面骑士响鬼"),
    (2006, "Kamen Rider Kabuto", "仮面ライダーカブト", "假面骑士甲斗"),
    (2007, "Kamen Rider Den-O", "仮面ライダー電王", "假面骑士电王"),
    (2008, "Kamen Rider Kiva", "仮面ライダーキバ", "假面骑士Kiva"),
    (2009, "Kamen Rider Decade", "仮面ライダーディケイド", "假面骑士帝骑"),
    (2009, "Kamen Rider W", "Kamen Rider Double", "仮面ライダーW", "假面骑士W"),
    (2010, "Kamen Rider OOO", "Kamen Rider Ozu", "仮面ライダーオーズ", "假面骑士OOO"),
    (2011, "Kamen Rider Fourze", "仮面ライダーフォーゼ", "假面骑士Fourze"),
    (2012, "Kamen Rider Wizard", "仮面ライダーウィザード", "假面骑士巫骑"),
    (2013, "Kamen Rider Gaim", "仮面ライダー鎧武", "假面骑士铠武"),
    (2014, "Kamen Rider Drive", "仮面ライダードライブ", "假面骑士驰骑"),
    (2015, "Kamen Rider Ghost", "仮面ライダーゴースト", "假面骑士Ghost"),
    (2016, "Kamen Rider Ex-Aid", "仮面ライダーエグゼイド", "假面骑士Ex-Aid"),
    (2017, "Kamen Rider Build", "仮面ライダービルド", "假面骑士创骑"),
    (2018, "Kamen Rider Zi-O", "仮面ライダージオウ", "假面骑士时王"),
    (2019, "Kamen Rider Zero-One", "仮面ライダーゼロワン", "假面骑士Zero-One"),
    (2020, "Kamen Rider Saber", "仮面ライダーセイバー", "假面骑士圣刃"),
    (2021, "Kamen Rider Revice", "仮面ライダーリバイス", "假面骑士利维斯"),
    (2022, "Kamen Rider Geats", "仮面ライダーギーツ", "假面骑士极狐"),
    (2023, "Kamen Rider Gotchard", "仮面ライダーガッチャード", "假面骑士歌查德"),
    (2024, "Kamen Rider Gavv", "仮面ライダーガヴ", "假面骑士加布"),
    (2025, "Kamen Rider Zeztz", "Kamen Rider ZEZTZ", "仮面ライダーゼッツ"),
)

SUPER_SENTAI_SERIES = (
    (1975, "Himitsu Sentai Gorenger"),
    (1977, "J.A.K.Q. Dengekitai", "JAKQ Dengekitai"),
    (1979, "Battle Fever J"),
    (1980, "Denshi Sentai Denziman"),
    (1981, "Taiyo Sentai Sun Vulcan"),
    (1982, "Dai Sentai Goggle-V", "Dai Sentai Goggle Five"),
    (1983, "Kagaku Sentai Dynaman"),
    (1984, "Choudenshi Bioman", "超電子バイオマン"),
    (1985, "Dengeki Sentai Changeman"),
    (1986, "Choushinsei Flashman"),
    (1987, "Hikari Sentai Maskman"),
    (1988, "Choujuu Sentai Liveman"),
    (1989, "Kousoku Sentai Turboranger"),
    (1990, "Chikyu Sentai Fiveman"),
    (1991, "Choujin Sentai Jetman"),
    (1992, "Kyoryu Sentai Zyuranger"),
    (1993, "Gosei Sentai Dairanger"),
    (1994, "Ninja Sentai Kakuranger"),
    (1995, "Chouriki Sentai Ohranger"),
    (1996, "Gekisou Sentai Carranger"),
    (1997, "Denji Sentai Megaranger"),
    (1998, "Seijuu Sentai Gingaman"),
    (1999, "Kyuukyuu Sentai GoGoFive", "Kyukyu Sentai GoGoFive"),
    (2000, "Mirai Sentai Timeranger"),
    (2001, "Hyakujuu Sentai Gaoranger"),
    (2002, "Ninpuu Sentai Hurricaneger"),
    (2003, "Bakuryuu Sentai Abaranger", "爆竜戦隊アバレンジャー", "爆龙战队暴连者"),
    (2004, "Tokusou Sentai Dekaranger"),
    (2005, "Mahou Sentai Magiranger"),
    (2006, "GoGo Sentai Boukenger", "Gogo Sentai Boukenger"),
    (2007, "Juken Sentai Gekiranger"),
    (2008, "Engine Sentai Go-onger"),
    (2009, "Samurai Sentai Shinkenger"),
    (2010, "Tensou Sentai Goseiger"),
    (2011, "Kaizoku Sentai Gokaiger"),
    (2012, "Tokumei Sentai Go-Busters"),
    (2013, "Zyuden Sentai Kyoryuger"),
    (2014, "Ressha Sentai ToQger"),
    (2015, "Shuriken Sentai Ninninger"),
    (2016, "Doubutsu Sentai Zyuohger"),
    (2017, "Uchu Sentai Kyuranger"),
    (2018, "Kaitou Sentai Lupinranger VS Keisatsu Sentai Patranger"),
    (2019, "Kishiryu Sentai Ryusoulger"),
    (2020, "Mashin Sentai Kiramager"),
    (2021, "Kikai Sentai Zenkaiger"),
    (2022, "Avataro Sentai Donbrothers"),
    (2023, "Ohsama Sentai King-Ohger"),
    (2024, "Bakuage Sentai Boonboomger"),
    (2025, "No.1 Sentai Gozyuger", "No. 1 Sentai Gozyuger"),
)

def choose_franchise_result(entry: tuple, results: list[dict]) -> dict | None:
    """从指定年份的 TMDB TV 搜索结果中选出白名单正剧。"""
    if not results:
        return None
    year = int(entry[0])
    aliases = [normalize_title(value) for value in entry[1:] if value]

    def is_non_main_title(result: dict) -> bool:
        raw_title = " ".join(
            str(result.get(key) or "") for key in ("name", "original_name")
        ).lower()
        normalized = normalize_title(raw_title)
        # TMDB 常把正剧的短篇、定格动画、谈话篇等排在正剧前面；这些不是主线 TV 正剧。
        excluded = (
            "stopmotion", "crossrail", "saythetalking", "talks", "nintality",
            "challenges", "special", "movie", "film", "side story", "spinoff",
            "spinoff", "miniseries", "short series", "shortfilm",
        )
        return ":" in raw_title or any(token in normalized for token in excluded)

    def score(result: dict) -> tuple[int, float]:
        if is_non_main_title(result):
            return -1000, 0
        names = [
            normalize_title(result.get("name") or ""),
            normalize_title(result.get("original_name") or ""),
        ]
        points = 0
        if any(name == alias for name in names for alias in aliases):
            points += 200
        elif any(alias in name or name in alias for name in names for alias in aliases if name and alias):
            points += 80
        if (result.get("first_air_date") or "")[:4] == str(year):
            points += 100
        if result.get("poster_path"):
            points += 5
        return points, float(result.get("popularity") or 0)

    best = max(results, key=score)
    return best if score(best)[0] >= 80 else None

def franchise_entry(entry: tuple) -> dict:
    return {"year": int(entry[0]), "aliases": list(entry[1:])}

def fetch_franchise_series(entries: tuple[tuple, ...], headers: dict, now: datetime) -> list[dict]:
    """按固定正剧白名单从 TMDB 搜索系列，排除电影、特别篇和衍生剧。"""
    today = now.strftime("%Y-%m-%d")
    resolved = []
    seen = set()
    for raw_entry in entries:
        entry = franchise_entry(raw_entry)
        if entry["year"] > now.year:
            continue
        result = None
        for query in entry["aliases"]:
            payload = get_json(
                f"{TMDB_API_BASE}/search/tv",
                params={
                    "query": query,
                    "language": "zh-CN",
                    "include_adult": "false",
                    "first_air_date_year": entry["year"],
                    "page": 1,
                },
                headers=headers,
            )
            result = choose_franchise_result(raw_entry, payload.get("results", []))
            if result:
                break
        if not result:
            print(f"警告：TMDB 未匹配到正剧：{entry['year']} {entry['aliases'][0]}")
            continue
        first_air_date = result.get("first_air_date") or ""
        if not first_air_date or first_air_date > today or first_air_date[:4] != str(entry["year"]):
            print(f"警告：TMDB 日期不符，跳过正剧：{entry['year']} {entry['aliases'][0]} -> {first_air_date}")
            continue
        tmdb_id = int(result["id"])
        if tmdb_id in seen:
            continue
        seen.add(tmdb_id)
        resolved.append(
            {
                "tmdb_id": tmdb_id,
                "tmdb_type": "tv",
                "title": result.get("name") or result.get("original_name") or entry["aliases"][0],
                "first_air_date": first_air_date,
                "poster_path": result.get("poster_path"),
            }
        )
    resolved.sort(key=lambda item: (item["first_air_date"], item["tmdb_id"]), reverse=True)
    return resolved

def write_franchise_feed(
    items: list[dict],
    name: str,
    base: str,
    now: datetime,
    watch_path: Path,
    cover_path: Path,
    selection_path: Path,
    feed_name: str = "",
):
    cover_candidates = [item for item in items if item.get("poster_path")]
    if len(cover_candidates) < 3:
        raise RuntimeError(f"{name} 可用海报不足 3 张，当前仅有 {len(cover_candidates)} 张")
    selected = select_daily_cover(cover_candidates, now, selection_path)
    make_cover(selected, now, cover_path)
    saved_name = str(load_json(watch_path, {}).get("name") or "").strip()
    final_name = str(feed_name or "").strip() or saved_name or f"{name}（{len(items)}部）"
    feed = {
        "name": final_name,
        "cover": f"{base}/{cover_path.name}",
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "videos": [
            {
                "tmdb_id": item["tmdb_id"],
                "tmdb_type": item["tmdb_type"],
                "title": item["title"],
                "sort": position,
            }
            for position, item in enumerate(items, start=1)
        ],
    }
    watch_path.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return selected

def latest_regular_season(data: dict, today) -> dict | None:
    """取得截至今天已上线的最新普通季，排除 specials（第 0 季）。"""
    seasons = []
    for season in data.get("seasons") or []:
        try:
            season_number = int(season.get("season_number") or 0)
        except (TypeError, ValueError):
            season_number = 0
        air_date = season.get("air_date") or ""
        if season_number <= 0 or not air_date or air_date > today.isoformat():
            continue
        seasons.append((air_date, season_number, season))
    if not seasons:
        return None
    return max(seasons, key=lambda value: (value[0], value[1]))[2]

def tmdb_is_regular_variety_episode(episode: dict) -> bool:
    try:
        episode_number = int(episode.get("episode_number") or 0)
    except (TypeError, ValueError):
        episode_number = 0
    if episode_number <= 0 or not episode.get("air_date"):
        return False
    title = str(episode.get("name") or "").lower()
    return not any(term.lower() in title for term in VARIETY_EXCLUDED_EPISODE_TERMS)

def fetch_tmdb_variety(headers: dict, now: datetime, limit: int = 50) -> list[dict]:
    """从 TMDB 获取本年度有新季或正片更新的中国大陆综艺。"""
    today = now.date()
    today_text = today.isoformat()
    year_start = f"{now.year}-01-01"
    recent_text = (today - timedelta(days=120)).isoformat()
    future_text = (today + timedelta(days=30)).isoformat()

    discovered = fetch_tmdb_discover(
        "tv",
        headers,
        {
            "language": "zh-CN",
            "sort_by": "popularity.desc",
            "first_air_date.lte": today_text,
            "with_origin_country": "CN",
            "with_genres": "10764|10767",
            "include_null_first_air_dates": "false",
        },
        limit=160,
        max_pages=8,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        details = list(
            executor.map(
                lambda item: get_json(
                    f"{TMDB_API_BASE}/tv/{int(item['id'])}",
                    params={"language": "zh-CN"},
                    headers=headers,
                ),
                discovered,
            )
        )

    candidates = []
    for item, detail in zip(discovered, details):
        countries = set(detail.get("origin_country") or [])
        genre_ids = {int(value.get("id")) for value in (detail.get("genres") or []) if value.get("id")}
        if "CN" not in countries or not genre_ids.intersection(TMDB_VARIETY_GENRE_IDS):
            continue
        season = latest_regular_season(detail, today)
        if not season:
            continue
        season_date = season.get("air_date") or ""
        if not year_start <= season_date <= today_text:
            continue
        candidates.append((item, detail, season))

    def load_season(value):
        item, detail, season = value
        season_number = int(season.get("season_number") or 0)
        payload = get_json(
            f"{TMDB_API_BASE}/tv/{int(item['id'])}/season/{season_number}",
            params={"language": "zh-CN"},
            headers=headers,
        )
        return item, detail, season, payload

    with ThreadPoolExecutor(max_workers=8) as executor:
        season_payloads = list(executor.map(load_season, candidates[:100]))

    results = []
    for item, detail, season, season_payload in season_payloads:
        regular_episodes = [
            episode
            for episode in (season_payload.get("episodes") or [])
            if tmdb_is_regular_variety_episode(episode)
            and (episode.get("air_date") or "") <= today_text
        ]
        if not regular_episodes:
            continue
        latest_episode = max(
            regular_episodes,
            key=lambda episode: (
                episode.get("air_date") or "",
                int(episode.get("episode_number") or 0),
            ),
        )
        latest_episode_date = latest_episode.get("air_date") or ""
        future_episodes = [
            episode
            for episode in (season_payload.get("episodes") or [])
            if tmdb_is_regular_variety_episode(episode)
            and today_text < (episode.get("air_date") or "") <= future_text
        ]
        next_episode_date = min(
            (episode.get("air_date") for episode in future_episodes),
            default="",
        )
        active_status = detail.get("status") in {"Returning Series", "In Production", "Pilot"}
        if not active_status and latest_episode_date < recent_text and not next_episode_date:
            continue
        poster_path = detail.get("poster_path") or season.get("poster_path") or item.get("poster_path")
        results.append(
            {
                "tmdb_id": int(detail["id"]),
                "tmdb_type": "tv",
                "title": detail.get("name") or item.get("name") or f"TMDB {detail['id']}",
                "first_air_date": detail.get("first_air_date") or "",
                "season_air_date": season.get("air_date") or "",
                "season_number": int(season.get("season_number") or 0),
                "latest_episode_date": latest_episode_date,
                "next_air_date": next_episode_date,
                "sort_date": latest_episode_date or season.get("air_date") or "",
                "poster_path": poster_path,
            }
        )

    results.sort(
        key=lambda item: (
            item["latest_episode_date"] == today_text,
            item["sort_date"],
            item["tmdb_id"],
        ),
        reverse=True,
    )
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

def detect_new_variety_today(
    items: list[dict],
    output_path: Path,
    now: datetime,
    state: dict,
) -> bool:
    """只有当天出现新季上线或正片更新时，才允许重排综艺片单。"""
    state_key = "variety_update_v2"
    previous = state.get(state_key)
    today = now.strftime("%Y-%m-%d")

    # 首次启用时不沿用旧状态，确保当天确实更新过的正片能触发一次排序。
    if previous is None:
        previous = {}

    current = {}
    has_new_update = False
    for item in items:
        season_date = item.get("season_air_date") or ""
        episode_date = item.get("latest_episode_date") or ""
        if not season_date and not episode_date:
            continue
        key = f"{item['tmdb_type']}:{item['tmdb_id']}"
        current[key] = {
            "season_air_date": season_date,
            "latest_episode_date": episode_date,
        }
        old = previous.get(key) if isinstance(previous.get(key), dict) else {}
        if (
            season_date == today and old.get("season_air_date") != today
        ) or (
            episode_date == today and old.get("latest_episode_date") != today
        ):
            has_new_update = True
    state[state_key] = current
    return has_new_update

def main():
    config = load_json(CONFIG_PATH, {})
    manual = load_json(MAPPING_PATH, {})
    cache = load_json(CACHE_PATH, {})
    release_state = load_json(RELEASE_STATE_PATH, {})
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    base = config["site_base_url"].rstrip("/")
    headers = tmdb_headers()

    japan_items = fetch_tmdb_japanese_anime(headers, now, limit=50)
    japan_cover_candidates = [item for item in japan_items if item.get("poster_path")]
    if len(japan_cover_candidates) < 3:
        raise RuntimeError(f"TMDB 当前日番海报不足 3 张，当前仅有 {len(japan_cover_candidates)} 张")
    japan_selected = select_daily_cover(japan_cover_candidates, now, JAPAN_SELECTION_PATH)
    make_cover(japan_selected, now, JAPAN_COVER_PATH)
    japan_previous_name = str(load_json(JAPAN_WATCH_PATH, {}).get("name") or "").strip()
    japan_watch = {
        "name": str(config.get("japan_name") or "").strip() or japan_previous_name or "厕纸",
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

    kamen_items = fetch_franchise_series(KAMEN_RIDER_SERIES, headers, now)
    kamen_selected = write_franchise_feed(
        kamen_items,
        "假面骑士正剧（2000年至今）",
        base,
        now,
        KAMEN_WATCH_PATH,
        KAMEN_COVER_PATH,
        KAMEN_SELECTION_PATH,
        str(config.get("kamen_rider_name") or "").strip(),
    )
    sentai_items = fetch_franchise_series(SUPER_SENTAI_SERIES, headers, now)
    sentai_selected = write_franchise_feed(
        sentai_items,
        "东映超级战队正剧（1975年至今）",
        base,
        now,
        SENTAI_WATCH_PATH,
        SENTAI_COVER_PATH,
        SENTAI_SELECTION_PATH,
        str(config.get("super_sentai_name") or "").strip(),
    )

    variety_items = fetch_tmdb_variety(headers, now, limit=50)
    variety_cover_candidates = [item for item in variety_items if item.get("poster_path")]
    variety_should_update = detect_new_variety_today(
        variety_items, WATCH_PATH, now, release_state
    )
    if not variety_should_update and VARIETY_WATCH_PATH.exists():
        # 没有当天新综艺时，视频列表和封面均保持原样。
        RELEASE_STATE_PATH.write_text(
            json.dumps(release_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"已更新日番 {len(japan_items)} 部、假面骑士正剧 {len(kamen_items)} 部、超级战队正剧 {len(sentai_items)} 部；"
            "综艺无当日新上线，保持综艺片单和封面不变。"
        )
        return
    if len(variety_cover_candidates) < 3:
        raise RuntimeError(f"TMDB 当前在播综艺海报不足 3 张，当前仅有 {len(variety_cover_candidates)} 张")
    variety_selected = select_daily_cover(variety_cover_candidates, now, VARIETY_SELECTION_PATH)
    make_cover(variety_selected, now, VARIETY_COVER_PATH)
    # 保留旧地址，避免已经填入 cover.gif 的用户丢图；两个文件内容保持一致。
    shutil.copyfile(VARIETY_COVER_PATH, COVER_PATH)
    variety_watch = {
        "name": (
            str(config.get("variety_name") or "").strip()
            or str(load_json(VARIETY_WATCH_PATH, {}).get("name") or "").strip()
            or f"国内流媒体热播更新综艺（{len(variety_items)}部）"
        ),
        "cover": f"{base}/cover-variety.gif",
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
    VARIETY_WATCH_PATH.write_text(
        json.dumps(variety_watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    RELEASE_STATE_PATH.write_text(
        json.dumps(release_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"已更新日番 {len(japan_items)} 部、假面骑士正剧 {len(kamen_items)} 部、超级战队正剧 {len(sentai_items)} 部；"
        f"已更新国内流媒体热播综艺 {len(variety_items)} 部；"
        f"综艺今日封面：{', '.join(item['title'] for item in variety_selected)}。"
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

