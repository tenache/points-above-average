"""Small hand-made pages in Basketball-Reference's layout, for the tests."""


def player(pid, name=None):
    return f'<a href="/players/{pid[0]}/{pid}.html">{name or pid}</a>'


def pbp_page(plays, away="AAA", home="HHH"):
    """plays: (period, clock, side, html) with side 'away' or 'home'."""
    rows = []
    period = 0
    for p, clock, side, html in plays:
        while period < p:
            period += 1
            rows.append(f'<tr class="thead" id="q{period}"><th colspan="6">{period} Q</th></tr>'
                        '<tr class="thead"><th>Time</th><th>A</th><th></th><th>Score</th><th></th><th>H</th></tr>')
        cells = [html, "&nbsp;"] if side == "away" else ["&nbsp;", "&nbsp;"]
        right = ["&nbsp;", html] if side == "home" else ["&nbsp;", "&nbsp;"]
        rows.append(f"<tr><td>{clock}</td><td>{cells[0]}</td><td>{cells[1]}</td><td>0-0</td>"
                    f"<td>{right[0]}</td><td>{right[1]}</td></tr>")
    return (f'<html><body><div class="scorebox"><a href="/teams/{away}/2027.html">A</a>'
            f'<a href="/teams/{home}/2027.html">H</a></div>'
            f'<table id="pbp">{"".join(rows)}</table></body></html>')


def totals_page(rows):
    """rows: (pid, name, team, games, fga, fta, pts)."""
    body = "".join(
        f'<tr><td data-stat="name_display">{player(pid, name)}</td>'
        f'<td data-stat="team_name_abbr">{team}</td><td data-stat="games">{g}</td>'
        f'<td data-stat="fga">{fga}</td><td data-stat="fta">{fta}</td><td data-stat="pts">{pts}</td></tr>'
        for pid, name, team, g, fga, fta, pts in rows)
    return f'<table id="totals_stats"><tbody>{body}</tbody></table>'
