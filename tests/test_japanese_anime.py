import copy
import importlib.util
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "update_watch", Path(__file__).resolve().parents[1] / "scripts" / "update_watch.py"
)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def anime(tmdb_id=1, premiere="2026-07-01", runtime=24):
    return {
        "id": tmdb_id, "name": f"作品{tmdb_id}", "origin_country": ["JP"],
        "genres": [{"id": 16}], "overview": "动画简介", "poster_path": "/poster.jpg",
        "first_air_date": premiere, "episode_run_time": [runtime],
        "last_episode_to_air": {"air_date": "2026-09-30", "runtime": runtime},
        "seasons": [{"season_number": 1, "air_date": premiere, "episode_count": 12}],
    }


class JapaneseAnimeTests(unittest.TestCase):
    def test_short_and_incomplete_details_are_rejected(self):
        for runtime in (1, 5, 14, 0, None):
            with self.subTest(runtime=runtime):
                self.assertIsNotNone(watch.japanese_anime_rejection_reason(anime(runtime=runtime), "2026-09-30"))
        for field in ("name", "overview", "poster_path", "genres", "first_air_date", "seasons"):
            detail = anime()
            del detail[field]
            with self.subTest(field=field):
                self.assertIsNotNone(watch.japanese_anime_rejection_reason(detail, "2026-09-30"))

    def test_normal_first_episode_and_episode_runtime_fallback_are_kept(self):
        detail = anime()
        detail["seasons"][0]["episode_count"] = 1
        detail["episode_run_time"] = []
        self.assertIsNone(watch.japanese_anime_rejection_reason(detail, "2026-09-30"))

    def test_specials_and_future_series_are_rejected(self):
        detail = anime()
        detail["seasons"][0]["season_number"] = 0
        self.assertIsNotNone(watch.japanese_anime_rejection_reason(detail, "2026-09-30"))
        self.assertIsNotNone(watch.japanese_anime_rejection_reason(anime(premiere="2026-10-01"), "2026-09-30"))

    def test_all_sources_pass_final_gate_and_keep_premiere_order(self):
        details = {1: anime(1), 2: anime(2, "2026-09-10"), 3: anime(3, runtime=3), 4: anime(4)}
        del details[4]["overview"]
        details[1]["first_air_date"] = "2023-01-01"
        details[1]["seasons"][0]["air_date"] = "2026-07-01"
        candidates = [{"tmdb_id": i, "title": d["name"]} for i, d in details.items() if i != 4]
        external = {"source": "bgm", "title": "缺失简介", "search_titles": ["missing"], "first_air_date": "2026-09-20"}
        resolved = {"tmdb_id": 4, "title": "缺失简介", "season_premiere_date": "2026-09-20", "_detail": details[4]}
        with patch.object(watch, "fetch_tmdb_japanese_anime", return_value=candidates), \
             patch.object(watch, "fetch_bangumi_anime", return_value=[external]), \
             patch.object(watch, "fetch_anilist_anime", return_value=[]), \
             patch.object(watch, "resolve_external_tv_to_tmdb", return_value=resolved), \
             patch.object(watch, "fetch_tv_detail", side_effect=lambda i, headers: copy.deepcopy(details[i])):
            result = watch.fetch_japanese_anime({}, datetime(2026, 9, 30))
        self.assertEqual([item["tmdb_id"] for item in result], [2, 1])
        self.assertEqual([item["sort_date"] for item in result], ["2026-09-10", "2026-07-01"])


if __name__ == "__main__":
    unittest.main()
