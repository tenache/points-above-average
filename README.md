# Points above average

How many points a player scores above the league average, per game and per attempt, for the current NBA season, updated every morning.

## The stat

**PAA per game = (the player's points − the league's points per attempt × his attempts) ÷ his games.** The leaderboard is ranked by it.

**PAA per attempt = the player's points per attempt − the league's points per attempt.**

Positive is better than average. If the league scores 1 point per attempt, a made 2 is +1, and a made 2 followed by a miss is 0.

An **attempt** is a field-goal attempt or a trip to the free-throw line:

- Two or three free throws in one trip count as one attempt, so 2/2 from the line equals a made 2.
- An and-one is one attempt: the extra free throw adds a point to the shot.
- Technical and flagrant free throws are left out, points included: they aren't the player's own shot. So are lone free throws after a take foul, an away-from-play foul, delay of game or defensive three seconds: the team picks who shoots them. A lone free throw after a loose-ball foul is the fouled player's own: one attempt.
- Turnovers don't count.

The league average is total points over total attempts, across every player this season, counted the same way.

## What the page shows

- **Leaderboard**, ranked by PAA per game: players with at least 5 points per *team* game (his season points over the games his team has played), so a good bench player can be compared with a star, and a player who stops playing drops off: 45 points in game 1 stays on the board for 9 team games.
- **Versus teammates**: the player's points per attempt minus the rest of his team's.
- **Last night**: who did especially well and who did badly (ranked by each player's points above average in the game, with his PAA per attempt), among players with at least 10 points in the game.
- **Scatter plots**: attempts or points per game against PAA per attempt, PAA per game or versus teammates.

## Data

Play-by-play from [Basketball-Reference](https://www.basketball-reference.com/), fetched politely (one request every few seconds, as its `robots.txt` asks) and only once per game. Each game's counts are saved in `data/`.

## Running it

- `python -m paa.update` fetches the games played since the last run and builds `site/data.json`; `--no-fetch` only builds; `--reparse --cache cache` parses every saved game again after a parser fix.
- The GitHub Action (`.github/workflows/update.yml`) runs every morning at 09:30 UTC, commits new games in `data/`, and publishes `site/` on GitHub Pages once the repository variable `PAGES_ENABLED` is `true` (Pages needs a public repository on a free plan).
- Each season: set `SEASON_END_YEAR` and `SEASON_LABEL` in `paa/update.py`. GitHub turns off scheduled workflows after 60 days without commits, so after the summer the schedule has to be turned on again in the Actions tab.
