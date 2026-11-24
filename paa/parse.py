"""Read Basketball-Reference pages into plain counts."""

import re

from bs4 import BeautifulSoup, Comment

PLAYER_HREF = re.compile(r"^/players/\w/(\w+)\.html$")
GAME_HREF = re.compile(r"^/boxscores/(\d{9}[A-Z]{3})\.html$")
TEAM_HREF = re.compile(r"^/teams/([A-Z]{3})/\d{4}\.html$")
FIELD_GOAL = re.compile(r"^(makes|misses) ([23])-pt\b")
FREE_THROW = re.compile(r"^(makes|misses) ([a-z ]*?)free throw(?: (\d) of (\d))?")
# Free throws that aren't the shooter's own scoring chance: left out, points included.
NOT_OWN_SHOT = ("technical", "flagrant")


def game_ids(schedule_html):
    """Ids of the games already played on a month's schedule page, in page order.

    Only played games have a box-score link, so games still to come are skipped.
    """
    soup = BeautifulSoup(schedule_html, "html.parser")
    ids = []
    for link in soup.select("table#schedule a[href]"):
        match = GAME_HREF.match(link["href"])
        if match and match.group(1) not in ids:
            ids.append(match.group(1))
    return ids


def _player_id(link):
    match = PLAYER_HREF.match(link.get("href", ""))
    return match.group(1) if match else None


def new_player():
    return {"team": None, "pts": 0, "att": 0, "fga": 0, "fgm2": 0, "fgm3": 0,
            "trips": 0, "fta": 0, "ftm": 0, "other_fta": 0, "other_ftm": 0, "name": None}


def game(pbp_html, game_id):
    """Per-player counts for one game, from its play-by-play page."""
    soup = BeautifulSoup(pbp_html, "html.parser")
    scorebox = soup.select_one("div.scorebox")
    teams = []
    for link in (scorebox or soup).select("a[href]"):
        match = TEAM_HREF.match(link["href"])
        if match and match.group(1) not in teams:
            teams.append(match.group(1))
        if len(teams) == 2:
            break
    if len(teams) != 2:
        raise ValueError(f"{game_id}: couldn't find the two teams")
    away, home = teams
    if game_id[-3:] != home:
        raise ValueError(f"{game_id}: home team {home} doesn't match the game id")

    table = soup.find("table", id="pbp")
    if table is None:
        raise ValueError(f"{game_id}: no play-by-play table")

    players = {}
    votes = {}  # player -> {team: plays}; his team is the column he acts in most
    # And-ones: a made field goal, then a foul drawn by the same shooter, then his lone free throw,
    # with no field-goal attempt in between. Any other lone free throw (technical, delay of game,
    # take foul, away-from-play foul...) is taken by whoever the team picks: not his own shot.
    made_by = None  # who made the latest field-goal attempt of the period, if it went in
    and_one = None  # that shooter, once he has drawn a shooting foul on the play
    # A loose-ball foul during a teammate's made basket gives the fouled player one free throw
    # of his own: (period, clock, player) of the latest loose-ball foul drawn.
    loose_ball = None
    period = 0
    unparsed = []

    def vote(link, team, weight):
        pid = _player_id(link)
        entry = players.setdefault(pid, new_player())
        entry["name"] = entry["name"] or link.get_text(strip=True)
        tally = votes.setdefault(pid, {})
        tally[team] = tally.get(team, 0) + weight
        return pid

    for row in table.find_all("tr"):
        if "thead" in (row.get("class") or []):
            # Each period opens with a header row that has an id (q1, q2...); column headers don't.
            if row.get("id"):
                period += 1
                made_by = and_one = None
            continue
        cells = row.find_all("td")
        if len(cells) != 6:
            continue
        clock = cells[0].get_text(strip=True)
        for index, team in ((1, away), (5, home)):
            cell = cells[index]
            text = cell.get_text(" ", strip=True)
            link = cell.find("a", href=PLAYER_HREF)
            if link is None:
                continue
            first = next((c for c in cell.contents if not (isinstance(c, str) and not c.strip())), None)
            lowered = text.lower()
            if " foul by " in f" {lowered}" or "ejected" in lowered:
                # Fouls and ejections say nothing about who played or for whom: some fouls sit in
                # the column of the team that drew them (shooting, personal), others in the
                # fouler's (offensive, loose ball, technical, even from the bench). They only
                # matter for and-ones and loose-ball free throws.
                links = cell.find_all("a", href=PLAYER_HREF)
                drawn = _player_id(links[1]) if "drawn by" in text and len(links) > 1 else None
                if lowered.startswith("shooting foul") and made_by and drawn == made_by:
                    and_one = made_by
                if lowered.startswith("loose ball foul") and drawn:
                    loose_ball = (period, clock, drawn)
                continue
            if lowered.startswith("turnover"):
                made_by = and_one = None
            # Everyone else named first in a column plays for that team (shooter, rebounder,
            # turnover...), and so do both players in a substitution.
            same_team = cell.find_all("a", href=PLAYER_HREF)[:2] if "enters the game for" in text else []
            for teammate in same_team:
                vote(teammate, team, 1)
            # The acting player is the first link, and the play starts right after it.
            if first is not link:
                continue
            pid = vote(link, team, 1)
            rest = ""
            for sibling in link.next_siblings:
                rest += sibling if isinstance(sibling, str) else sibling.get_text()
            rest = rest.strip()
            shot = FIELD_GOAL.match(rest)
            throw = FREE_THROW.match(rest)
            if not shot and not throw:
                continue
            stats = players[pid]
            made = (shot or throw).group(1) == "makes"
            if shot:
                stats["fga"] += 1
                stats["att"] += 1
                if made:
                    stats["pts"] += int(shot.group(2))
                    stats["fgm" + shot.group(2)] += 1
                made_by = pid if made else None
                and_one = None
                continue
            kind = throw.group(2)
            if any(word in kind for word in NOT_OWN_SHOT):
                stats["other_fta"] += 1
                stats["other_ftm"] += made
                continue
            if throw.group(3) is None:
                unparsed.append(rest)
            number, total = (int(throw.group(3)), int(throw.group(4))) if throw.group(3) else (1, 1)
            own_lone = and_one == pid or loose_ball == (period, clock, pid)
            if total == 1 and not own_lone:
                stats["other_fta"] += 1
                stats["other_ftm"] += made
                continue
            stats["fta"] += 1
            stats["ftm"] += made
            stats["pts"] += made
            if total == 1 and and_one == pid:
                and_one = None  # the and-one's point goes to the shot: no new attempt
            elif number == 1:
                loose_ball = None if total == 1 else loose_ball
                stats["trips"] += 1  # a trip of two or three is one attempt
                stats["att"] += 1
    for pid, tally in votes.items():
        players[pid]["team"] = max(tally, key=tally.get)
    players = {pid: p for pid, p in players.items() if p["team"]}
    # A page with missing plays would be saved wrong for good: check it adds up to the final score.
    scores = [s.get_text(strip=True) for s in (scorebox.select("div.score") if scorebox else [])]
    if len(scores) == 2 and all(x.isdigit() for x in scores):
        counted = {away: 0, home: 0}
        for p in players.values():
            counted[p["team"]] = counted.get(p["team"], 0) + p["pts"] + p["other_ftm"]
        if [counted[away], counted[home]] != [int(x) for x in scores]:
            raise ValueError(f"{game_id}: plays add up to {counted[away]}-{counted[home]}, "
                             f"the final score is {scores[0]}-{scores[1]}")
    return {"id": game_id, "away": away, "home": home, "players": players, "unparsed": unparsed}


def season_totals(totals_html):
    """Names and official totals per player: {pid: {name, team, g, fga, fta, pts}}.

    Players traded mid-season have one row per team plus a combined row (2TM, 3TM...)
    listed first; the combined row is the one kept, with the latest team.
    """
    soup = BeautifulSoup(totals_html, "html.parser")
    table = soup.find("table", id="totals_stats")
    if table is None:
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            if 'id="totals_stats"' in comment:
                table = BeautifulSoup(comment, "html.parser").find("table", id="totals_stats")
                break
    if table is None:
        raise ValueError("no totals table")
    out = {}
    for row in table.select("tbody tr"):
        name_cell = row.find(attrs={"data-stat": "name_display"})
        if name_cell is None or name_cell.find("a") is None:
            continue
        pid = _player_id(name_cell.find("a"))

        def number(stat):
            cell = row.find(attrs={"data-stat": stat})
            text = cell.get_text(strip=True) if cell else ""
            return int(text) if text.isdigit() else 0

        team_cell = row.find(attrs={"data-stat": "team_name_abbr"})
        team = team_cell.get_text(strip=True) if team_cell else ""
        if pid in out:
            if not re.fullmatch(r"\dTM", team):
                out[pid]["team"] = team
            continue
        out[pid] = {"name": name_cell.find("a").get_text(strip=True), "team": team,
                    "g": number("games"), "fga": number("fga"), "fta": number("fta"),
                    "pts": number("pts")}
    return out
