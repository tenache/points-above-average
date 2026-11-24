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
    last_make = {}  # player -> (period, clock) of his last made field goal, to spot and-ones
    period = 0
    unparsed = []
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
        for index, team in ((1, away), (5, home)):
            cell = cells[index]
            link = cell.find("a", href=PLAYER_HREF)
            if link is None:
                continue
            # Who played: the first player in a team's column is on that team (shooter,
            # rebounder, fouler...), and so are both players in a substitution.
            text = cell.get_text(" ", strip=True)
            same_team = [link] + (cell.find_all("a", href=PLAYER_HREF)[1:2]
                                  if "enters the game for" in text else [])
            for teammate in same_team:
                entry = players.setdefault(_player_id(teammate), new_player())
                entry["team"] = entry["team"] or team
                entry["name"] = entry["name"] or teammate.get_text(strip=True)
            # The acting player is the first link, and the play starts right after it.
            first = next((c for c in cell.contents if not (isinstance(c, str) and not c.strip())), None)
            if first is not link:
                continue
            rest = ""
            for sibling in link.next_siblings:
                rest += sibling if isinstance(sibling, str) else sibling.get_text()
            rest = rest.strip()
            shot = FIELD_GOAL.match(rest)
            throw = FREE_THROW.match(rest)
            if not shot and not throw:
                continue
            pid = _player_id(link)
            stats = players[pid]
            made = (shot or throw).group(1) == "makes"
            if shot:
                stats["fga"] += 1
                stats["att"] += 1
                if made:
                    value = int(shot.group(2))
                    stats["pts"] += value
                    stats["fgm" + shot.group(2)] += 1
                    last_make[pid] = (period, clock)
                continue
            kind = throw.group(2)
            if any(word in kind for word in NOT_OWN_SHOT):
                stats["other_fta"] += 1
                stats["other_ftm"] += made
                continue
            stats["fta"] += 1
            stats["ftm"] += made
            stats["pts"] += made
            if throw.group(3) is None:
                unparsed.append(rest)
                continue
            number, total = int(throw.group(3)), int(throw.group(4))
            if number != 1:
                continue
            if total >= 2:
                stats["trips"] += 1
                stats["att"] += 1
            elif last_make.get(pid) != (period, clock):
                # A lone free throw that isn't an and-one is its own scoring chance.
                stats["trips"] += 1
                stats["att"] += 1
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
