"""From per-game counts to the numbers the page shows."""

from collections import defaultdict

SEASON_MIN_PPG = 6  # leaderboard and versus-teammates minimum, points per game
NIGHT_MIN_PTS = 10  # last-night minimum, points in the game


def game_date(game_id):
    return f"{game_id[:4]}-{game_id[4:6]}-{game_id[6:8]}"


def ratio(points, attempts):
    return points / attempts if attempts else None


def league_average(games):
    points = sum(p["pts"] for g in games for p in g["players"].values())
    attempts = sum(p["att"] for g in games for p in g["players"].values())
    return ratio(points, attempts)


def season(games, names=None):
    """One row per player for the season, sorted by PAA per attempt (best first)."""
    names = names or {}
    league = league_average(games)
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
        row["qualified"] = row["ppg"] >= SEASON_MIN_PPG
        out.append(row)
    out.sort(key=lambda r: -r["paa_pa"])
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
    out = []
    for (pid, team), s in stints.items():
        rest_pts, rest_att = s["team_pts"] - s["pts"], s["team_att"] - s["att"]
        if not s["att"] or not rest_att:
            continue
        ppa, rest = s["pts"] / s["att"], rest_pts / rest_att
        out.append({"id": pid, "name": s["name"], "team": team, "gp": s["gp"],
                    "ppg": s["pts"] / s["gp"], "att": s["att"], "ppa": ppa, "rest_ppa": rest,
                    "diff": ppa - rest, "qualified": s["pts"] / s["gp"] >= SEASON_MIN_PPG})
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
                             "ppa": ppa, "paa_pa": ppa - league,
                             "qualified": p["pts"] >= NIGHT_MIN_PTS})
        rows.sort(key=lambda r: -r["paa_pa"])
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
