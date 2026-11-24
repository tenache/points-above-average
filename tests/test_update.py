import json

import pytest

from paa import fetch, update
from tests.pages import pbp_page, player, totals_page

GOOD, BAD = "202611010HHH", "202611020HHH"


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.requests_made = 0

    def get(self, path, use_cache=True):
        self.requests_made += 1
        return self.pages[path]


def schedule(*ids):
    return '<table id="schedule">' + "".join(
        f'<tr><td><a href="/boxscores/{gid}.html">Box Score</a></td></tr>' for gid in ids) + "</table>"


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "DATA", tmp_path / "data")
    monkeypatch.setattr(update, "SITE", tmp_path / "site")
    monkeypatch.setattr(update, "months_to_check", lambda saved, today: ["november"])
    return tmp_path / "data"


def pages(schedule_ids, games):
    out = {fetch.schedule_path(update.SEASON_END_YEAR, "november"): schedule(*schedule_ids),
           fetch.totals_path(update.SEASON_END_YEAR): totals_page([("aaaa01", "Ann A", "AAA", 1, 1, 0, 2)])}
    out.update({fetch.pbp_path(gid): html for gid, html in games.items()})
    return out


def test_a_bad_game_is_skipped_and_the_others_are_saved(data):
    good = pbp_page([(1, "11:00.0", "away", f"{player('aaaa01')} makes 2-pt jump shot from 8 ft")])
    failed = update.fetch_new(FakeFetcher(pages([BAD, GOOD], {BAD: "<html></html>", GOOD: good})), 10)
    assert len(failed) == 1 and failed[0].startswith(BAD)
    assert sorted(p.stem for p in (data / "games").glob("*.json")) == [GOOD]
    assert json.loads((data / "players.json").read_text(encoding="utf-8")) == {"aaaa01": "Ann A"}
    assert not list(data.rglob("*.tmp"))


def test_a_schedule_that_no_longer_lists_saved_games_fails_loudly(data):
    (data / "games").mkdir(parents=True)
    (data / "games" / f"{GOOD}.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="layout"):
        update.fetch_new(FakeFetcher(pages([], {})), 10)


def test_build_refuses_to_publish_an_empty_page(data):
    with pytest.raises(SystemExit):
        update.build()


def test_build_writes_the_page_data(data):
    good = pbp_page([(1, "11:00.0", "away", f"{player('aaaa01')} makes 2-pt jump shot from 8 ft"),
                     (1, "10:00.0", "home", f"{player('hhhh01')} misses 2-pt jump shot from 8 ft")])
    update.fetch_new(FakeFetcher(pages([GOOD], {GOOD: good})), 10)
    page = update.build(log=lambda *_: None)
    assert page["league_ppa"] == 1 and page["last_night"] == "2026-11-01"
    assert [r["name"] for r in page["players"]] == ["Ann A", "hhhh01"]
