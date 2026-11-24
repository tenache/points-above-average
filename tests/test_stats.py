from datetime import date

import pytest

from paa import parse, stats, update


def line(team, pts, att, **extra):
    p = parse.new_player()
    p.update(team=team, pts=pts, att=att, fga=att, **extra)
    return p


def game(gid, away, home, players):
    return {"id": gid, "away": away, "home": home, "players": players, "unparsed": []}


def test_the_examples_with_an_average_of_one():
    # League: 10 points on 10 attempts. A made 2 is +1; a made 2 and a miss is 0.
    games = [game("202611010HHH", "AAA", "HHH", {
        "one": line("AAA", 2, 1), "two": line("AAA", 2, 2), "rest": line("HHH", 6, 7)})]
    league, rows = stats.season(games)
    by_id = {r["id"]: r for r in rows}
    assert league == 1
    assert by_id["one"]["paa_pa"] == 1 and by_id["one"]["paa"] == 1
    assert by_id["two"]["paa_pa"] == 0 and by_id["two"]["paa"] == 0
    assert [r["id"] for r in rows][0] == "one"


def test_leaderboard_minimum_is_points_per_team_game():
    # Thomas's example: 45 points in game 1, then out. 45 / 9 team games = 5 (still on);
    # 45 / 10 = 4.5 (off).
    first = game("202611010HHH", "AAA", "HHH", {"star": line("AAA", 45, 20), "mate": line("AAA", 10, 10)})
    rest = [game(f"202611{d:02d}0HHH", "AAA", "HHH", {"mate": line("AAA", 10, 10)}) for d in range(2, 11)]
    _, rows = stats.season([first] + rest[:8])
    star = {r["id"]: r for r in rows}["star"]
    assert (star["team_gp"], star["qualified"]) == (9, True)
    _, rows = stats.season([first] + rest)
    star = {r["id"]: r for r in rows}["star"]
    assert (star["gp"], star["team_gp"], star["pts_per_team_game"], star["qualified"]) == (1, 10, 4.5, False)
    mates = {r["id"]: r for r in stats.versus_teammates([first] + rest)}
    assert not mates["star"]["qualified"] and mates["star"]["team_gp"] == 10


def test_a_traded_player_counts_his_old_team_until_the_trade_then_the_new_one():
    # 20 points a game for 4 games with AAA, then 2 games with BBB (whose season is 6 games long):
    # 120 points over 4 + 2 team games, not over BBB's 6.
    games = [game(f"2026110{d}0HHH", "AAA", "HHH", {"t": line("AAA", 20, 10), "m": line("AAA", 5, 5)})
             for d in range(1, 5)]
    games += [game(f"2026110{d}0HHH", "BBB", "HHH", {"b": line("BBB", 5, 5)}) for d in range(1, 5)]
    games += [game(f"2026110{d}0HHH", "BBB", "HHH", {"t": line("BBB", 0, 5), "b": line("BBB", 5, 5)})
              for d in (5, 6)]
    _, rows = stats.season(games)
    traded = {r["id"]: r for r in rows}["t"]
    assert (traded["team"], traded["team_gp"]) == ("BBB", 6)
    stints = {(r["id"], r["team"]): r for r in stats.versus_teammates(games)}
    assert stints[("t", "AAA")]["team_gp"] == 4 and stints[("t", "BBB")]["team_gp"] == 2


def test_players_without_attempts_count_games_but_get_no_row():
    games = [game("202611010HHH", "AAA", "HHH", {"a": line("AAA", 10, 5), "b": line("AAA", 0, 0)}),
             game("202611020HHH", "AAA", "HHH", {"a": line("AAA", 0, 0)})]
    _, rows = stats.season(games)
    assert [(r["id"], r["gp"], r["ppg"]) for r in rows] == [("a", 2, 5)]


def test_versus_teammates_uses_only_his_games_and_his_team():
    games = [
        game("202611010HHH", "AAA", "HHH", {"star": line("AAA", 30, 20), "mate": line("AAA", 10, 10),
                                            "opp": line("HHH", 50, 10)}),
        game("202611020HHH", "AAA", "HHH", {"mate": line("AAA", 100, 10)}),
    ]
    rows = {r["id"]: r for r in stats.versus_teammates(games)}
    assert rows["star"]["rest_ppa"] == 1  # only the first game's teammate, not the 100 points
    assert rows["star"]["diff"] == pytest.approx(0.5)
    assert "opp" not in rows  # his team had nobody else, the other team's players aren't teammates


def test_a_player_alone_on_his_team_has_no_teammates_row():
    games = [game("202611010HHH", "AAA", "HHH", {"solo": line("AAA", 10, 5), "opp": line("HHH", 5, 5)})]
    assert stats.versus_teammates(games) == []


def test_traded_player_gets_one_row_per_team():
    games = [game("202611010HHH", "AAA", "HHH", {"t": line("AAA", 10, 5), "m": line("AAA", 5, 5)}),
             game("202611020HHH", "BBB", "HHH", {"t": line("BBB", 10, 10), "n": line("BBB", 10, 5)})]
    rows = stats.versus_teammates(games)
    assert sorted((r["id"], r["team"]) for r in rows if r["id"] == "t") == [("t", "AAA"), ("t", "BBB")]
    _, season = stats.season(games)
    assert {r["id"]: r for r in season}["t"]["team"] == "BBB"


def test_nights_use_the_league_average_through_that_night():
    games = [game("202611010HHH", "AAA", "HHH", {"a": line("AAA", 10, 10), "h": line("HHH", 10, 10)}),
             game("202611020HHH", "AAA", "HHH", {"a": line("AAA", 30, 10), "h": line("HHH", 10, 10)})]
    nights = stats.nights(games)
    assert nights["2026-11-01"]["league_ppa"] == 1
    assert nights["2026-11-02"]["league_ppa"] == pytest.approx(60 / 40)
    rows = {r["id"]: r for r in nights["2026-11-02"]["rows"]}
    assert rows["a"]["paa_pa"] == pytest.approx(3 - 1.5)
    assert rows["a"]["opp"] == "HHH" and rows["h"]["opp"] == "AAA"
    assert rows["a"]["qualified"] and rows["h"]["qualified"]
    assert not {r["id"]: r for r in stats.nights(
        [game("202611030HHH", "AAA", "HHH", {"x": line("AAA", 9, 3)})])["2026-11-03"]["rows"]}["x"]["qualified"]


def test_check_reports_differences_with_official_totals():
    games = [game("202611010HHH", "AAA", "HHH", {"a": line("AAA", 10, 5, fta=2, other_fta=1, other_ftm=1)})]
    ok = {"a": {"name": "A", "g": 1, "fga": 5, "fta": 3, "pts": 11}}
    assert stats.check(games, ok) == []
    off = {"a": {"name": "A", "g": 1, "fga": 6, "fta": 3, "pts": 11}}
    assert stats.check(games, off) == [{"id": "a", "name": "A", "diff": {"fga": -1}}]


@pytest.mark.parametrize("today, expected", [
    (date(2026, 9, 30), []),
    (date(2026, 10, 25), ["october"]),
    (date(2026, 11, 24), ["october", "november"]),
    (date(2027, 1, 3), ["october", "november", "december", "january"]),
    (date(2027, 8, 1), ["october", "november", "december", "january", "february", "march", "april", "may", "june"]),
])
def test_months_to_check(today, expected):
    assert update.months_to_check(today) == expected


def test_paa_per_game_is_the_season_total_over_his_games_and_orders_the_rows():
    # League: 40 points on 40 attempts = 1.0. Volume shooter: 30 on 20 in each of 2 games, +10 a game.
    # Efficient bench player: 6 on 2 in 1 game, +4 a game but a far better rate.
    games = [game("202611010HHH", "AAA", "HHH", {"vol": line("AAA", 30, 20), "bench": line("AAA", 6, 2),
                                                  "h": line("HHH", 0, 0)}),
             game("202611020HHH", "AAA", "HHH", {"vol": line("AAA", 30, 20), "miss": line("HHH", 0, 16)})]
    league, rows = stats.season(games)
    assert league == 66 / 58
    by_id = {r["id"]: r for r in rows}
    assert by_id["vol"]["paa_pg"] == by_id["vol"]["paa"] / 2
    assert [r["id"] for r in rows] == sorted(by_id, key=lambda k: -by_id[k]["paa_pg"])
    assert by_id["bench"]["paa_pa"] > by_id["vol"]["paa_pa"] and rows[0]["id"] == "vol"


def test_a_night_row_carries_the_game_s_points_above_average():
    rows = stats.nights([game("202611010HHH", "AAA", "HHH", {"a": line("AAA", 12, 6), "h": line("HHH", 6, 6)})])
    row = {r["id"]: r for r in rows["2026-11-01"]["rows"]}["a"]
    assert row["paa"] == 12 - 1.5 * 6
