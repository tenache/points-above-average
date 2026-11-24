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
# Fouls after which the lone free throw is taken by whoever the team picks, logged as a plain
# "free throw 1 of 1": technicals (defensive three seconds, delay of game...), take fouls and
# away-from-play fouls.
OTHER_SHOOTER_FOUL = re.compile(r"\btech(nical)? foul\b|\btake foul\b|\baway from play foul\b")


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
    votes = {}  # player -> {team: weight}; his team is decided at the end of the game
    pending_other = {}  # (period, clock) -> lone free throws someone other than a shooter takes
    last_attempt = None  # (player, made, period) of the latest field-goal attempt, to spot and-ones
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
            continue
        cells = row.find_all("td")
        if len(cells) != 6:
            continue
        clock = cells[0].get_text(strip=True)
        for index, team, other in ((1, away, home), (5, home, away)):
            cell = cells[index]
            text = cell.get_text(" ", strip=True)
            lowered = text.lower()
            if OTHER_SHOOTER_FOUL.search(lowered) and "rescinded" not in lowered:
                pending_other[(period, clock)] = pending_other.get((period, clock), 0) + 1
            link = cell.find("a", href=PLAYER_HREF)
            if link is None:
                continue
            first = next((c for c in cell.contents if not (isinstance(c, str) and not c.strip())), None)
            if " foul by " in f" {lowered}":
                # Fouls sit in the column of the team that drew them, so the fouler plays for
                # the other team. A weak vote: only used if he does nothing else all game.
                if first is not link:
                    vote(link, other, 0.001)
                continue
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
                last_attempt = (pid, made, period)
                continue
            kind = throw.group(2)
            if any(word in kind for word in NOT_OWN_SHOT):
                stats["other_fta"] += 1
                stats["other_ftm"] += made
                if "technical" in kind and pending_other.get((period, clock)):
                    pending_other[(period, clock)] -= 1
                continue
            if throw.group(3) is None:
                unparsed.append(rest)
            number, total = (int(throw.group(3)), int(throw.group(4))) if throw.group(3) else (1, 1)
            if total == 1 and last_attempt != (pid, True, period) and pending_other.get((period, clock)):
                # A lone free throw after a technical, a defensive three seconds, a take foul or an
                # away-from-play foul: the team picks the shooter, so it isn't his own shot.
                pending_other[(period, clock)] -= 1
                stats["other_fta"] += 1
                stats["other_ftm"] += made
                continue
            stats["fta"] += 1
            stats["ftm"] += made
            stats["pts"] += made
            if number != 1:
                continue
            if total >= 2 or last_attempt != (pid, True, period):
                # A trip of two or three is one attempt; so is a lone free throw that isn't
                # an and-one (an and-one follows his own make, with no shot in between).
                stats["trips"] += 1
                stats["att"] += 1
    for pid, tally in votes.items():
        players[pid]["team"] = max(tally, key=tally.get)
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
