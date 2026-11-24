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
        (2, "3:10.0", "home", f"Shooting foul by {player(H)} (drawn by {player(A)})"),
        (2, "3:10.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["trips"], p["fta"]) == (3, 1, 0, 1)


def test_and_one_logged_a_second_later_is_still_an_and_one():
    p = counts([
        (1, "4:13.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (1, "4:12.0", "home", f"Shooting foul by {player(H)} (drawn by {player(A)})"),
        (1, "4:12.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["trips"]) == (3, 1, 0)


def test_lone_free_throw_without_a_foul_on_his_make_is_left_out():
    # A make, then 26 seconds later a lone free throw with no foul drawn on the shot: not an and-one,
    # so the team picked the shooter (technical, delay of game, take foul...).
    p = counts([
        (2, "3:10.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (2, "2:44.0", "away", f"Delay tech foul by Team"),
        (2, "2:44.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["fta"], p["other_fta"], p["other_ftm"]) == (2, 1, 0, 1, 1)


@pytest.mark.parametrize("foul", [
    "Def 3 sec tech foul by Team",
    f"Technical foul by {player(H)}",
    f"Personal take foul by {player(H)} (drawn by {player(A)})",
    f"Away from play foul by {player(H)} (drawn by {player(B)})",
])
def test_lone_free_throw_after_a_technical_or_take_foul_is_left_out(foul):
    p = counts([
        (3, "6:00.0", "home", f"{player(H)} misses 2-pt layup at rim"),
        (3, "0:11.0", "away", foul),
        (3, "0:11.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["fta"], p["other_fta"], p["other_ftm"]) == (0, 0, 0, 1, 1)


def test_a_foul_drawn_by_someone_else_is_not_an_and_one():
    p = counts([
        (3, "1:00.0", "away", f"{player(A)} makes 3-pt jump shot from 25 ft"),
        (3, "0:58.0", "away", f"Personal foul by {player(H)} (drawn by {player(B)})"),
        (3, "0:58.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["other_ftm"]) == (3, 1, 1)


def test_two_shot_trip_after_a_technical_still_counts():
    p = counts([
        (3, "0:11.0", "away", f"Technical foul by {player(H)}"),
        (3, "0:11.0", "away", f"{player(A)} makes technical free throw"),
        (3, "0:11.0", "away", f"{player(A)} makes free throw 1 of 2"),
        (3, "0:11.0", "away", f"{player(A)} makes free throw 2 of 2"),
    ])[A]
    assert (p["pts"], p["att"], p["other_ftm"]) == (2, 1, 1)


def test_and_one_check_looks_at_the_period_too():
    p = counts([
        (1, "0:01.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (2, "12:00.0", "home", f"Shooting foul by {player(H)} (drawn by {player(A)})"),
        (2, "12:00.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["att"], p["other_fta"]) == (1, 1)


def test_a_foul_drawn_after_a_turnover_is_not_an_and_one():
    p = counts([
        (1, "4:17.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (1, "4:00.0", "home", f"Turnover by {player(H)} (bad pass)"),
        (1, "3:43.0", "away", f"Personal foul by {player(H)} (drawn by {player(A)})"),
        (1, "3:43.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["att"], p["other_ftm"]) == (1, 1)


def test_a_teammate_s_turnover_doesnt_cancel_an_and_one_already_drawn():
    p = counts([
        (3, "0:21.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (3, "0:21.0", "home", f"Shooting foul by {player(H)} (drawn by {player(A)})"),
        (3, "0:21.0", "away", f"Turnover by {player(B)} (offensive foul)"),
        (3, "0:21.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["other_ftm"]) == (3, 1, 0)


def test_a_fouled_miss_doesnt_leave_an_and_one_behind():
    p = counts([
        (1, "5:00.0", "away", f"{player(A)} makes 2-pt layup at rim"),
        (1, "5:00.0", "home", f"Shooting foul by {player(H)} (drawn by {player(A)})"),
        (1, "5:00.0", "away", f"{player(A)} makes free throw 1 of 2"),
        (1, "5:00.0", "away", f"{player(A)} makes free throw 2 of 2"),
        (1, "4:30.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["att"], p["other_ftm"]) == (2, 1)


def test_lone_free_throw_after_a_loose_ball_foul_is_his_own():
    p = counts([
        (1, "6:00.0", "away", f"{player(B)} makes 2-pt layup at rim"),
        (1, "6:00.0", "home", f"Loose ball foul by {player(H)} (drawn by {player(A)})"),
        (1, "6:00.0", "away", f"{player(A)} makes free throw 1 of 1"),
    ])[A]
    assert (p["pts"], p["att"], p["trips"], p["other_fta"]) == (1, 1, 1, 0)


def test_an_ejection_is_not_a_game_played():
    p = counts([
        (1, "4:00.0", "away", f"{player(A)} misses 2-pt layup at rim"),
        (2, "6:00.0", "home", f"{player(H)} ejected from game"),
    ])
    assert H not in p


def test_plays_must_add_up_to_the_final_score():
    page = pbp_page([(1, "11:00.0", "away", f"{player(A)} makes 2-pt jump shot from 8 ft")])
    good = page.replace('</div>', '<div class="score">2</div><div class="score">0</div></div>', 1)
    assert parse.game(good, "202611220HHH")["players"][A]["pts"] == 2
    with pytest.raises(ValueError, match="final score"):
        parse.game(page.replace('</div>', '<div class="score">4</div><div class="score">0</div></div>', 1), "202611220HHH")


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


def test_fouls_dont_decide_teams():
    # Shooting and personal fouls sit in the fouled team's column; offensive, loose-ball and
    # technical fouls in the fouler's. Either way the team comes from his other plays.
    p = counts([
        (1, "4:00.0", "home", f"Shooting foul by {player(A)} (drawn by {player(H)})"),
        (1, "4:00.0", "home", f"{player(H)} makes free throw 1 of 2"),
        (1, "3:50.0", "away", f"Offensive foul by {player(A)} (drawn by {player(H)})"),
        (1, "3:30.0", "away", f"{player(A)} misses 2-pt layup at rim"),
    ])
    assert p[H]["team"] == "HHH" and p[A]["team"] == "AAA"


def test_a_technical_from_the_bench_is_not_a_game_played():
    p = counts([
        (1, "4:00.0", "away", f"{player(A)} misses 2-pt layup at rim"),
        (2, "6:00.0", "home", f"Technical foul by {player(H)}"),
    ])
    assert H not in p


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
