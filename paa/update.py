"""Fetch the games played since the last run, then rebuild the page's data.

    python -m paa.update              # fetch what's new, then build site/data.json
    python -m paa.update --no-fetch   # build from data/ only
    python -m paa.update --no-fetch --reparse --cache cache   # parse saved games again, from cached pages
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import fetch, parse, stats

SEASON_END_YEAR = 2027
SEASON_LABEL = "2026-27"
MONTHS = ["october", "november", "december", "january", "february", "march", "april", "may", "june"]
MONTH_NUMBERS = [10, 11, 12, 1, 2, 3, 4, 5, 6]

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"


def months_to_check(today):
    """Every schedule page of the season so far (October through this month, at most nine),
    so a game that failed in an earlier month is still tried again."""
    first, last = (SEASON_END_YEAR - 1, 10), (SEASON_END_YEAR, 6)
    end = min((today.year, today.month), last)
    months = []
    year, month = first
    while (year, month) <= end:
        months.append(MONTHS[MONTH_NUMBERS.index(month)])
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def write_json(path, value, **options):
    """Write to a temporary file, then rename, so a crash never leaves half a file."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, **options), encoding="utf-8")
    os.replace(temporary, path)


def load_games():
    """This season's saved games (an earlier season's files are left alone)."""
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((DATA / "games").glob("*.json")) if this_season(p.stem)]


def save_game(fetcher, gid):
    game = parse.game(fetcher.get(fetch.pbp_path(gid)), gid)
    if game["unparsed"]:
        print(f"{gid}: free throws without 'n of m': {game['unparsed']}")
    write_json(DATA / "games" / f"{gid}.json", game, indent=1, sort_keys=True, ensure_ascii=False)


def this_season(game_id):
    return f"{SEASON_END_YEAR - 1}1001" <= game_id[:8] < f"{SEASON_END_YEAR}1001"


def skippable(error):
    """A page that can't be parsed, or is missing (404), is one bad game: skip it and go on.
    Anything else (refused, rate limited, timing out, a server error) stops the run."""
    if isinstance(error, ValueError):
        return True
    response = getattr(error, "response", None)
    return response is not None and response.status_code == 404


def fetch_new(fetcher, max_games, log=print):
    """Fetch the games played since the last run. A game that fails is skipped and
    tried again next run; the others are still saved, and the run fails at the end."""
    games_dir = DATA / "games"
    games_dir.mkdir(parents=True, exist_ok=True)
    saved = {p.stem for p in games_dir.glob("*.json") if this_season(p.stem)}
    today = datetime.now(timezone.utc).date()
    played = []
    for month in months_to_check(today):
        played += parse.game_ids(fetcher.get(fetch.schedule_path(SEASON_END_YEAR, month), use_cache=False))
    missing = saved - set(played)
    if missing:
        # Every month is checked, so a working parser must list every saved game.
        raise RuntimeError(f"the schedule pages don't list {len(missing)} saved games, e.g. {min(missing)}: "
                           "has Basketball-Reference's layout changed?")
    new = [gid for gid in played if gid not in saved]
    log(f"{len(played)} games played so far, {len(new)} new")
    failed = []
    for gid in new[:max_games]:
        try:
            save_game(fetcher, gid)
        except Exception as error:  # noqa: BLE001 - one bad page mustn't block the rest
            if not skippable(error):
                raise
            failed.append(f"{gid}: {error}")
    if len(new) > max_games:
        log(f"stopped after {max_games} games; run again for the remaining {len(new) - max_games}")
    totals = parse.season_totals(fetcher.get(fetch.totals_path(SEASON_END_YEAR), use_cache=False))
    names = {pid: t["name"] for pid, t in totals.items()}
    write_json(DATA / "players.json", names, indent=1, sort_keys=True, ensure_ascii=False)
    write_json(DATA / "totals.json", totals, indent=1, sort_keys=True, ensure_ascii=False)
    return failed


def reparse(cache_dir, log=print):
    """Parse every saved game again (after a parser fix), from cached pages only: never online."""
    fetcher = fetch.Fetcher(cache_dir=cache_dir, offline=True)
    failed = []
    for path in sorted((DATA / "games").glob("*.json")):
        if not this_season(path.stem):
            continue
        try:
            save_game(fetcher, path.stem)
        except (ValueError, FileNotFoundError) as error:
            failed.append(f"{path.stem}: {error}")
    log(f"parsed {len(list((DATA / 'games').glob('*.json')))} saved games again")
    return failed


def rounded(value):
    if isinstance(value, float):
        return round(value, 6)  # enough that the page rounds the true value, not a rounded one
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v) for v in value]
    return value


def build(log=print):
    games = load_games()
    if not games:
        raise SystemExit("no games in data/: nothing to publish")
    names_file, totals_file = DATA / "players.json", DATA / "totals.json"
    names = json.loads(names_file.read_text(encoding="utf-8")) if names_file.exists() else {}
    totals = json.loads(totals_file.read_text(encoding="utf-8")) if totals_file.exists() else {}
    league, season_rows = stats.season(games, names)
    nights = stats.nights(games, names)
    for night in nights.values():
        night["rows"] = [r for r in night["rows"] if r["qualified"]]
    problems = stats.check(games, totals) if totals else []
    if problems:
        log(f"{len(problems)} players differ from the official totals, first ones: {problems[:5]}")
    page = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "season": SEASON_LABEL,
        "games": len(games),
        "last_night": max(nights),
        "league_ppa": league,
        "min_pts_per_team_game": stats.SEASON_MIN_PTS_PER_TEAM_GAME,
        "min_night_pts": stats.NIGHT_MIN_PTS,
        "players": season_rows,
        "teammates": stats.versus_teammates(games, names),
        "nights": nights,
        "check": {"players_checked": len(totals), "mismatches": problems},
    }
    SITE.mkdir(exist_ok=True)
    write_json(SITE / "data.json", rounded(page), ensure_ascii=False, separators=(",", ":"))
    log(f"built site/data.json: {len(games)} games, league {league:.4f} points per attempt")
    return page


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-fetch", action="store_true", help="build from data/ only")
    parser.add_argument("--max-games", type=int, default=400, help="new games to fetch in one run")
    parser.add_argument("--reparse", action="store_true", help="parse every saved game again")
    parser.add_argument("--cache", help="folder that keeps fetched pages between runs")
    args = parser.parse_args()
    if args.reparse and not args.cache:
        parser.error("--reparse needs --cache: it only reads pages already fetched")
    fetcher = fetch.Fetcher(cache_dir=args.cache)
    failed = []
    if args.reparse:
        failed += reparse(args.cache)
    if not args.no_fetch:
        failed += fetch_new(fetcher, args.max_games)
    if fetcher.requests_made:
        print(f"{fetcher.requests_made} requests to Basketball-Reference")
    build()
    if failed:
        raise SystemExit(f"{len(failed)} games failed and will be tried again next run: {failed}")


if __name__ == "__main__":
    main()
