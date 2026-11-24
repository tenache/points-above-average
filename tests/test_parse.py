import pytest

from paa import parse
from tests.pages import pbp_page, player, totals_page

A, B, H = "aaaa01", "bbbb01", "hhhh01"


def counts(plays, game_id="202611220HHH"):
    return parse.game(pbp_page(plays), game_id)["players"]


def test_field_goals():
    p = counts([
        (1, "11:00.0", "away", f"{player(A)} makes 2-pt jump shot from 8 ft"),
        (1, "10:00.0", "away", f"{player(A)} misses 3-pt jump shot from 25 ft (block by {player(H)})"),
        (1, "9:00.0", "away", f"{player(A)} makes 3-pt jump shot from 25 ft (assist by {player(B)})"),
    ])[A]
    assert (p["pts"], p["att"], p["fga"], p["fgm2"], p["fgm3"]) == (5, 3, 3, 1, 1)


def test_two_shot_trip_is_one_attempt():
    p = counts([
        (1, "5:00.0", "home", f"{player(H)} makes free throw 1 of 2"),
        (1, "5:00.0", "home", f"{player(H)} makes free throw 2 of 2"),
    ])[H]
    assert (p["pts"], p["att"], p["trips"], p["fta"]) == (2, 1, 1, 2)


def test_three_shot_trip_is_one_attempt():
    p = counts([(1, "5:00.0", "home", f"{player(H)} misses free throw {n} of 3") for n in (1, 2, 3)])[H]
    assert (p["pts"], p["att"], p["trips"], p["fta"]) == (0, 1, 1, 3)


def test_and_one_adds_a_point_not_an_attempt():
    p = counts([
        (2, "3:10.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (2, "3:10.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["trips"]) == (3, 1, 0)


def test_lone_free_throw_without_a_make_is_an_attempt():
    p = counts([
        (2, "3:10.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (2, "1:05.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["trips"]) == (3, 2, 1)


def test_and_one_check_looks_at_the_period_too():
    p = counts([
        (1, "3:10.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (2, "3:10.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert p["att"] == 2


def test_technical_and_flagrant_free_throws_are_left_out():
    p = counts([
        (1, "8:00.0", "home", f"{player(H)} makes technical free throw"),
        (1, "7:00.0", "home", f"{player(H)} makes flagrant free throw 1 of 2"),
        (1, "7:00.0", "home", f"{player(H)} misses flagrant free throw 2 of 2"),
    ])[H]
    assert (p["pts"], p["att"], p["fta"]) == (0, 0, 0)
    assert (p["other_fta"], p["other_ftm"]) == (3, 2)


def test_teams_come_from_the_column():
    p = counts([
        (1, "11:00.0", "away", f"{player(A)} makes 2-pt jump shot from 8 ft"),
        (1, "10:00.0", "home", f"{player(H)} misses 2-pt jump shot from 8 ft"),
    ])
    assert p[A]["team"] == "AAA" and p[H]["team"] == "HHH"


def test_players_who_never_shoot_still_played():
    p = counts([
        (1, "6:00.0", "away", f"{player(B)} enters the game for {player(A)}"),
        (1, "5:00.0", "home", f"Defensive rebound by {player(H)}"),
        (1, "4:00.0", "home", f"{player(H)} misses 2-pt layup (block by {player('zzzz01')})"),
    ])
    assert set(p) == {A, B, H}
    assert p[A]["team"] == p[B]["team"] == "AAA" and p[A]["att"] == 0


def test_opponents_named_in_a_play_are_not_counted_for_that_team():
    p = counts([
        (1, "4:00.0", "away", f"Shooting foul by {player(A)} (drawn by {player(H)})"),
        (1, "4:00.0", "home", f"{player(H)} makes free throw 1 of 2"),
    ])
    assert p[H]["team"] == "HHH"


def test_home_team_must_match_the_game_id():
    with pytest.raises(ValueError):
        parse.game(pbp_page([], home="XXX"), "202611220HHH")


def test_schedule_lists_only_played_games():
    html = ('<table id="schedule"><tr><td><a href="/boxscores/202611220ATL.html">Box Score</a></td></tr>'
            '<tr><td><a href="/teams/ATL/2027.html">ATL</a></td></tr>'
            '<tr><td><a href="/boxscores/202611220ATL.html">again</a></td></tr></table>')
    assert parse.game_ids(html) == ["202611220ATL"]


def test_traded_players_keep_the_combined_row_and_the_latest_team():
    html = totals_page([(A, "Ann A", "2TM", 10, 100, 20, 120), (A, "Ann A", "BOS", 6, 60, 10, 70),
                        (A, "Ann A", "NYK", 4, 40, 10, 50), (B, "Bo B", "MIA", 3, 9, 0, 8)])
    totals = parse.season_totals(html)
    assert totals[A] == {"name": "Ann A", "team": "NYK", "g": 10, "fga": 100, "fta": 20, "pts": 120}
    assert totals[B]["team"] == "MIA"
