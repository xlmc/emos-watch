import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "short_drama_watch", Path(__file__).resolve().parents[1] / "scripts" / "update_watch.py"
)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def entry(title="虚颜"):
    return {"title": title, "year": 2022, "aliases": [], "format": "landscape", "source_url": "https://www.mgtv.com/h/457600.html"}


def detail(title="虚颜", tmdb_id=1, popularity=10):
    return {
        "id": tmdb_id, "name": title, "first_air_date": "2022-09-23",
        "origin_country": ["CN"], "original_language": "zh", "genres": [{"id": 18}],
        "overview": "真人剧情短剧", "poster_path": "/poster.jpg", "number_of_episodes": 18,
        "episode_run_time": [12], "seasons": [{"season_number": 1, "air_date": "2022-09-23", "episode_count": 18}],
        "popularity": popularity,
    }


class ShortDramaTests(unittest.TestCase):
    def test_verified_finished_drama_is_kept(self):
        self.assertIsNone(watch.short_drama_rejection_reason(detail(), entry(), "2026-10-03"))

    def test_vertical_wrong_year_and_incomplete_data_are_rejected(self):
        for changes in ({"format": "portrait"}, {"source_url": ""}, {"year": 2024}):
            with self.subTest(changes=changes):
                self.assertIsNotNone(watch.short_drama_rejection_reason(detail(), {**entry(), **changes}, "2026-10-03"))
        for changes in ({"name": "虚颜花絮"}, {"episode_run_time": []}, {"episode_run_time": [45]}, {"genres": [{"id": 16}]}, {"overview": ""}, {"poster_path": None}, {"number_of_episodes": 0}):
            with self.subTest(changes=changes):
                self.assertIsNotNone(watch.short_drama_rejection_reason({**detail(), **changes}, entry(), "2026-10-03"))

    def test_search_skips_wrong_title_and_sorts_hotter_first(self):
        entries = [entry("虚颜"), entry("念念无明")]
        def get_json(url, *, params, headers):
            title = params["query"]
            return {"results": [{"id": 99, "name": title + "花絮"}, {"id": 1 if title == "虚颜" else 2, "name": title}]}
        def tv_detail(tmdb_id, headers):
            return detail("虚颜" if tmdb_id == 1 else "念念无明", tmdb_id, tmdb_id * 10)
        with patch.object(watch, "get_json", side_effect=get_json), patch.object(watch, "fetch_tv_detail", side_effect=tv_detail) as fetched:
            result = watch.fetch_curated_short_dramas({}, datetime(2026, 10, 3), entries)
        self.assertEqual([value["tmdb_id"] for value in result], [2, 1])
        self.assertEqual(fetched.call_count, 2)

    def test_generated_feed_and_cover_are_connected(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(watch, "make_cover") as cover:
            folder = Path(temp)
            values = [{"tmdb_id": 1, "tmdb_type": "tv", "title": "虚颜", "poster_path": "/poster.jpg"}]
            watch.write_franchise_feed(values, "横屏精品短剧", "https://example.com", datetime(2026, 10, 3), folder / "watch-short-drama.json", folder / "cover-short-drama.gif", folder / "selection.json", allow_small_cover=True)
            feed = json.loads((folder / "watch-short-drama.json").read_text(encoding="utf-8"))
            self.assertEqual(feed["cover"], "https://example.com/cover-short-drama.gif")
            self.assertEqual(feed["videos"][0]["sort"], 1)
            self.assertEqual(len(cover.call_args.args[0]), 3)


if __name__ == "__main__":
    unittest.main()
