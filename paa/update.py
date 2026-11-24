"""Fetch the games played since the last run, then rebuild the page's data.

    python -m paa.update              # fetch what's new, then build site/data.json
    python -m paa.update --no-fetch   # build from data/ only
"""

import argparse
import json
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


def months_to_check(saved_ids, today):
    """Schedule pages worth fetching: from the month of the latest saved game
    (or the season's start) through the current month."""
    first, last = (SEASON_END_YEAR - 1, 10), (SEASON_END_YEAR, 6)
    end = min((today.year, today.month), last)
    start = first
    if saved_ids:
        latest = max(saved_ids)  # ids start with the date, so the largest is the latest
        start = max(first, (int(latest[:4]), int(latest[4:6])))
    months = []
    year, month = start
    while (year, month) <= end:
        months.append(MONTHS[MONTH_NUMBERS.index(month)])
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def load_games():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "games").glob("*.json"))]


def fetch_new(fetcher, max_games, log=print):
    games_dir = DATA / "games"
    games_dir.mkdir(parents=True, exist_ok=True)
    saved = {p.stem for p in games_dir.glob("*.json")}
    today = datetime.now(timezone.utc).date()
    played = []
    for month in months_to_check(saved, today):
        played += parse.game_ids(fetcher.get(fetch.schedule_path(SEASON_END_YEAR, month), use_cache=False))
    new = [gid for gid in played if gid not in saved]
    log(f"{len(played)} games played in the months checked, {len(new)} new")
    for gid in new[:max_games]:
        game = parse.game(fetcher.get(fetch.pbp_path(gid)), gid)
        if game["unparsed"]:
            log(f"{gid}: free throws without 'n of m': {game['unparsed']}")
        (games_dir / f"{gid}.json").write_text(json.dumps(game, indent=1, sort_keys=True), encoding="utf-8")
    if len(new) > max_games:
        log(f"stopped after {max_games} games; run again for the remaining {len(new) - max_games}")
    totals = parse.season_totals(fetcher.get(fetch.totals_path(SEASON_END_YEAR), use_cache=False))
    names = {pid: t["name"] for pid, t in totals.items()}
    (DATA / "players.json").write_text(json.dumps(names, indent=1, sort_keys=True, ensure_ascii=False),
                                       encoding="utf-8")
    (DATA / "totals.json").write_text(json.dumps(totals, indent=1, sort_keys=True, ensure_ascii=False),
                                      encoding="utf-8")
    return len(new) - max_games if len(new) > max_games else 0


def rounded(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v) for v in value]
    return value


def build(log=print):
    games = load_games()
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
        "last_night": max(nights) if nights else None,
        "league_ppa": league,
        "min_ppg": stats.SEASON_MIN_PPG,
        "min_night_pts": stats.NIGHT_MIN_PTS,
        "players": season_rows,
        "teammates": stats.versus_teammates(games, names),
        "nights": nights,
        "check": {"players_checked": len(totals), "mismatches": problems},
    }
    SITE.mkdir(exist_ok=True)
    (SITE / "data.json").write_text(json.dumps(rounded(page), ensure_ascii=False, separators=(",", ":")),
                                    encoding="utf-8")
    log(f"built site/data.json: {len(games)} games, league {league:.4f} points per attempt"
        if league else "built site/data.json: no games yet")
    return page


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-fetch", action="store_true", help="build from data/ only")
    parser.add_argument("--max-games", type=int, default=400, help="new games to fetch in one run")
    parser.add_argument("--cache", help="folder that keeps fetched pages between runs")
    args = parser.parse_args()
    if not args.no_fetch:
        fetcher = fetch.Fetcher(cache_dir=args.cache)
        fetch_new(fetcher, args.max_games)
        print(f"{fetcher.requests_made} requests to Basketball-Reference")
    build()


if __name__ == "__main__":
    main()
