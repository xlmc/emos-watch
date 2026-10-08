"""One-off TMDB matching report. Does not generate or modify watch feeds."""

import concurrent.futures
import datetime
import json
import os
from pathlib import Path
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "sorting-results"
TOKEN = os.environ["TMDB_API_TOKEN"].strip()


def normalize(title):
    return "".join(c for c in unicodedata.normalize("NFKC", title).casefold() if c.isalnum())


def search(query):
    params = urllib.parse.urlencode({"query": query, "language": "zh-CN", "include_adult": "false"})
    request = urllib.request.Request(
        f"https://api.themoviedb.org/3/search/tv?{params}",
        headers={"Authorization": TOKEN if TOKEN.lower().startswith("bearer ") else f"Bearer {TOKEN}"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)["results"]
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(int(error.headers.get("Retry-After", "3")))


def match(entry):
    title, year, aliases = entry
    query_title = re.sub(r"（.*?）", "", title)
    names = list(dict.fromkeys([query_title, *aliases.split(",")]))
    expected = {normalize(name) for name in names}
    found = {}
    related = {}
    for query in names:
        for item in search(query):
            item_names = {normalize(item.get("name", "")), normalize(item.get("original_name", ""))}
            if not expected.intersection(item_names) or 16 not in item.get("genre_ids", []):
                continue
            candidate = {
                "tmdb_id": item["id"], "name": item.get("name"),
                "original_name": item.get("original_name"), "first_air_date": item.get("first_air_date"),
                "popularity": item["popularity"], "vote_count": item["vote_count"],
                "url": f"https://www.themoviedb.org/tv/{item['id']}",
            }
            related[item["id"]] = candidate
            if not year or (item.get("first_air_date") or "")[:4] == year:
                found[item["id"]] = candidate
        if year and len(found) == 1:
            break
    # Keep uncertain editions unresolved, even when only one search hit exists.
    uncertain = "具体版本待定" in title or (not year and any(word in title for word in ("旧版", "早期版", "经典版")))
    if len(found) == 1 and not uncertain:
        return {"title": title, "status": "matched", **next(iter(found.values()))}
    return {"title": title, "status": "ambiguous" if found else "unmatched", "candidates": list(related.values())}


def main():
    entries = [line.split("|", 2) for line in (ROOT / "tools/childhood-animation-candidates.txt").read_text(encoding="utf-8").splitlines() if line]
    if len(entries) != 148 or len({entry[0] for entry in entries}) != 148:
        raise ValueError("Expected the 148 distinct user-selected candidates")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(match, entries))
    ranked = sorted((row for row in rows if row["status"] == "matched"), key=lambda row: (row["popularity"], row["vote_count"]), reverse=True)
    pending = [row for row in rows if row["status"] != "matched"]
    updated = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report = {"updated_at": updated, "candidate_count": len(rows), "matched_count": len(ranked), "pending_count": len(pending), "sort": "popularity descending, then vote_count descending", "ranked": ranked, "pending": pending}
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "childhood-animation-sorted.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 童年动画 TMDB 热度排序", "", f"数据时间：{updated}", "", f"候选 {len(rows)}；匹配并排序 {len(ranked)}；待确认 {len(pending)}。全部候选保留，不筛除，不修改现有片单。", "", "## 已匹配：热度由高到低", "", "| 排名 | 候选名称 | TMDB 名称 | 首播日期 | 当前热度 | 评分人数 | 条目 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for rank, row in enumerate(ranked, 1):
        cells = [str(rank), row["title"], row["name"], row["first_air_date"] or "", str(row["popularity"]), str(row["vote_count"]), f"[TMDB {row['tmdb_id']}]({row['url']})"]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    lines.extend(["", "## 待确认：未赋予热度排名", "", "有多个版本、年份不符或未找到精确条目；不等于没有资源。", ""])
    for row in pending:
        candidates = "; ".join(f"[{item['name']} / {item['first_air_date'] or '日期缺失'} / {item['tmdb_id']}]({item['url']})" for item in row["candidates"])
        lines.append(f"- {row['title']}：{candidates or '未找到精确匹配'}")
    (OUTPUT / "childhood-animation-sorted.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"候选 {len(rows)}；已匹配 {len(ranked)}；待确认 {len(pending)}")


if __name__ == "__main__":
    main()
