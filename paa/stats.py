"""From per-game counts to the numbers the page shows."""

from collections import defaultdict

# Leaderboard and versus-teammates minimum: his points over his team's games this season, so a
# player who stops playing falls off (45 points in game 1 drops below 5 after 9 more team games).
SEASON_MIN_PTS_PER_TEAM_GAME = 5
NIGHT_MIN_PTS = 10  # last-night minimum, points in the game


def game_date(game_id):
    return f"{game_id[:4]}-{game_id[4:6]}-{game_id[6:8]}"


def ratio(points, attempts):
    return points / attempts if attempts else None


def stint_team_games(games):
    """{(player, team): his team's games that count for him there}. A player's team games are
    his team's games this season; for a traded player, his old team's games until his first game
    for the new one, then the new team's from there on."""
    dates = defaultdict(list)  # team -> dates of its games
    first = defaultdict(dict)  # player -> {team: date of his first game for it}
    for g in sorted(games, key=lambda g: g["id"]):
        date = g["id"][:8]
        dates[g["away"]].append(date)
        dates[g["home"]].append(date)
        for pid, p in g["players"].items():
            first[pid].setdefault(p["team"], date)
    out = {}
    for pid, teams in first.items():
        order = sorted(teams, key=teams.get)
        for i, team in enumerate(order):
            start = teams[team] if i else ""
            end = teams[order[i + 1]] if i + 1 < len(order) else "99999999"
            out[(pid, team)] = sum(start <= d < end for d in dates[team])
    return out


def league_average(games):
    points = sum(p["pts"] for g in games for p in g["players"].values())
    attempts = sum(p["att"] for g in games for p in g["players"].values())
    return ratio(points, attempts)


def season(games, names=None):
    """One row per player for the season, sorted by PAA per game (best first)."""
    names = names or {}
    league = league_average(games)
    played = stint_team_games(games)
    rows = {}
    for g in sorted(games, key=lambda g: g["id"]):
        for pid, p in g["players"].items():
            row = rows.setdefault(pid, {"id": pid, "name": names.get(pid) or p["name"],
                                        "team": p["team"], "gp": 0, "pts": 0, "att": 0})
            row["team"] = p["team"]  # the latest team, for traded players
            row["gp"] += 1
            row["pts"] += p["pts"]
            row["att"] += p["att"]
    out = []
    for row in rows.values():
        if not row["att"]:
            continue
        row["ppg"] = row["pts"] / row["gp"]
        row["apg"] = row["att"] / row["gp"]
        row["ppa"] = row["pts"] / row["att"]
        row["paa_pa"] = row["ppa"] - league
        row["paa"] = row["pts"] - league * row["att"]
        row["paa_pg"] = row["paa"] / row["gp"]
        row["team_gp"] = sum(n for (p, _), n in played.items() if p == row["id"])
        row["pts_per_team_game"] = row["pts"] / row["team_gp"]
        row["qualified"] = row["pts_per_team_game"] >= SEASON_MIN_PTS_PER_TEAM_GAME
        out.append(row)
    out.sort(key=lambda r: -r["paa_pg"])
    return league, out


def versus_teammates(games, names=None):
    """One row per player and team: his points per attempt minus his teammates',
    counting only the games he played for that team. Sorted by that gap."""
    names = names or {}
    stints = defaultdict(lambda: {"gp": 0, "pts": 0, "att": 0, "team_pts": 0, "team_att": 0})
    for g in games:
        team_totals = defaultdict(lambda: [0, 0])
        for p in g["players"].values():
            team_totals[p["team"]][0] += p["pts"]
            team_totals[p["team"]][1] += p["att"]
        for pid, p in g["players"].items():
            stint = stints[(pid, p["team"])]
            stint["name"] = names.get(pid) or p["name"]
            stint["gp"] += 1
            stint["pts"] += p["pts"]
            stint["att"] += p["att"]
            stint["team_pts"] += team_totals[p["team"]][0]
            stint["team_att"] += team_totals[p["team"]][1]
    played = stint_team_games(games)
    out = []
    for (pid, team), s in stints.items():
        rest_pts, rest_att = s["team_pts"] - s["pts"], s["team_att"] - s["att"]
        if not s["att"] or not rest_att:
            continue
        ppa, rest = s["pts"] / s["att"], rest_pts / rest_att
        out.append({"id": pid, "name": s["name"], "team": team, "gp": s["gp"],
                    "ppg": s["pts"] / s["gp"], "att": s["att"], "ppa": ppa, "rest_ppa": rest,
                    "diff": ppa - rest, "team_gp": played[(pid, team)],
                    "qualified": s["pts"] / played[(pid, team)] >= SEASON_MIN_PTS_PER_TEAM_GAME})
    out.sort(key=lambda r: -r["diff"])
    return out


def nights(games, names=None):
    """{date: rows} with every player's game line, PAA per attempt measured against
    the league average through that date, so a night's numbers never change later."""
    names = names or {}
    by_date = defaultdict(list)
    for g in games:
        by_date[game_date(g["id"])].append(g)
    out = {}
    points = attempts = 0
    for date in sorted(by_date):
        for g in by_date[date]:
            for p in g["players"].values():
                points += p["pts"]
                attempts += p["att"]
        league = ratio(points, attempts)
        rows = []
        for g in by_date[date]:
            for pid, p in g["players"].items():
                if not p["att"]:
                    continue
                opponent = g["home"] if p["team"] == g["away"] else g["away"]
                ppa = p["pts"] / p["att"]
                rows.append({"id": pid, "name": names.get(pid) or p["name"], "team": p["team"],
                             "opp": opponent, "game": g["id"], "pts": p["pts"], "att": p["att"],
                             "ppa": ppa, "paa_pa": ppa - league, "paa": p["pts"] - league * p["att"],
                             "qualified": p["pts"] >= NIGHT_MIN_PTS})
        rows.sort(key=lambda r: -r["paa"])
        out[date] = {"league_ppa": league, "rows": rows}
    return out


def check(games, totals):
    """Players whose parsed season totals differ from Basketball-Reference's own."""
    mine = defaultdict(lambda: {"fga": 0, "fta": 0, "pts": 0, "g": 0})
    for g in games:
        for pid, p in g["players"].items():
            m = mine[pid]
            m["g"] += 1
            m["fga"] += p["fga"]
            m["fta"] += p["fta"] + p["other_fta"]
            m["pts"] += p["pts"] + p["other_ftm"]
    problems = []
    for pid, official in totals.items():
        m = mine.get(pid, {"fga": 0, "fta": 0, "pts": 0, "g": 0})
        diff = {k: m[k] - official[k] for k in ("g", "fga", "fta", "pts") if m[k] != official[k]}
        if diff:
            problems.append({"id": pid, "name": official["name"], "diff": diff})
    for pid in mine.keys() - totals.keys():
        problems.append({"id": pid, "name": pid, "diff": {"missing_from_totals": True}})
    return problems
