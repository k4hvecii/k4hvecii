#!/usr/bin/env python3
import datetime as dt
import html
import json
import os
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets/profile/profile.template.svg"
OUTPUT = ROOT / "assets/profile/profile.svg"
USERNAME = "k4hvecii"

token = os.environ.get("GITHUB_TOKEN")
if not token:
    raise SystemExit("GITHUB_TOKEN is required")

now = dt.datetime.now(dt.timezone.utc)
start = now - dt.timedelta(days=364)

query = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER) {
      totalCount
      nodes {
        isFork
        stargazerCount
      }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

payload = json.dumps({
    "query": query,
    "variables": {
        "login": USERNAME,
        "from": start.isoformat(),
        "to": now.isoformat(),
    },
}).encode()

request = urllib.request.Request(
    "https://api.github.com/graphql",
    data=payload,
    headers={
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "k4-profile-renderer",
    },
)

with urllib.request.urlopen(request, timeout=30) as response:
    body = json.load(response)

if body.get("errors"):
    raise SystemExit("GitHub GraphQL error: " + json.dumps(body["errors"]))

user = body["data"]["user"]
collection = user["contributionsCollection"]
calendar = collection["contributionCalendar"]
repos = user["repositories"]

non_fork_repos = [r for r in repos["nodes"] if not r["isFork"]]
stars = sum(int(r["stargazerCount"]) for r in non_fork_repos)

day_counts = {}
for week in calendar["weeks"]:
    for day in week["contributionDays"]:
        day_counts[day["date"]] = int(day["contributionCount"])

cursor = start.date()
end_date = now.date()
longest = 0
run = 0
while cursor <= end_date:
    if day_counts.get(cursor.isoformat(), 0) > 0:
        run += 1
        longest = max(longest, run)
    else:
        run = 0
    cursor += dt.timedelta(days=1)

max_count = max(day_counts.values(), default=0)
colors = ["#17110d", "#463226", "#6a4935", "#936342", "#c18458"]

def level(count: int) -> int:
    if count <= 0 or max_count <= 0:
        return 0
    ratio = count / max_count
    if ratio <= 0.25:
        return 1
    if ratio <= 0.50:
        return 2
    if ratio <= 0.75:
        return 3
    return 4

heatmap = []
x0, y0, step, size = 116, 2238, 19, 13
for week_index, week in enumerate(calendar["weeks"][-53:]):
    for day in week["contributionDays"]:
        date_obj = dt.date.fromisoformat(day["date"])
        row = (date_obj.weekday() + 1) % 7
        count = int(day["contributionCount"])
        x = x0 + week_index * step
        y = y0 + row * 18
        title = html.escape(f"{day['date']}: {count} contributions")
        heatmap.append(
            f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="3" '
            f'fill="{colors[level(count)]}"><title>{title}</title></rect>'
        )

values = {
    "{{CONTRIB_TOTAL}}": str(calendar["totalContributions"]),
    "{{COMMITS}}": str(collection["totalCommitContributions"]),
    "{{PRS}}": str(collection["totalPullRequestContributions"]),
    "{{REPOS}}": str(len(non_fork_repos)),
    "{{STARS}}": str(stars),
    "{{STREAK}}": str(longest),
    "{{UPDATED}}": now.strftime("%Y-%m-%d"),
    "{{HEATMAP}}": "\n    ".join(heatmap),
}

svg = TEMPLATE.read_text(encoding="utf-8")
for key, value in values.items():
    svg = svg.replace(key, value)

OUTPUT.write_text(svg, encoding="utf-8")
print(
    "profile stats:",
    f"contributions={values['{{CONTRIB_TOTAL}}']}",
    f"commits={values['{{COMMITS}}']}",
    f"prs={values['{{PRS}}']}",
    f"repos={values['{{REPOS}}']}",
    f"stars={values['{{STARS}}']}",
    f"streak={values['{{STREAK}}']}",
)
