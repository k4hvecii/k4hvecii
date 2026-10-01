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
STATS_OUTPUT = ROOT / "data/github-stats.json"
USERNAME = "k4hvecii"

def load_json(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))

def esc(value):
    return html.escape(str(value), quote=False)

profile = load_json("profile.json")
systems = load_json("systems.json")
projects = load_json("projects.json")
stack = load_json("stack.json")

token = os.environ.get("GITHUB_TOKEN")
if not token:
    raise SystemExit("GITHUB_TOKEN is required")

now = dt.datetime.now(dt.timezone.utc)
start = now - dt.timedelta(days=364)

query = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    followers { totalCount }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        url
        isFork
        isArchived
        stargazerCount
        forkCount
        pushedAt
        primaryLanguage { name color }
      }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            weekday
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
repos = [r for r in user["repositories"]["nodes"] if not r["isFork"] and not r["isArchived"]]
stars = sum(int(r["stargazerCount"]) for r in repos)

days = []
day_counts = {}
weekday_counts = [0, 0, 0, 0, 0, 0, 0]
for week in calendar["weeks"]:
    for day in week["contributionDays"]:
        count = int(day["contributionCount"])
        item = {"date": day["date"], "weekday": int(day["weekday"]), "count": count}
        days.append(item)
        day_counts[day["date"]] = count
        weekday_counts[item["weekday"]] += count

today = now.date()
cursor = today if day_counts.get(today.isoformat(), 0) > 0 else today - dt.timedelta(days=1)
current_streak = 0
while day_counts.get(cursor.isoformat(), 0) > 0:
    current_streak += 1
    cursor -= dt.timedelta(days=1)

cursor = start.date()
longest = 0
run = 0
while cursor <= today:
    if day_counts.get(cursor.isoformat(), 0) > 0:
        run += 1
        longest = max(longest, run)
    else:
        run = 0
    cursor += dt.timedelta(days=1)

active_days = [d for d in days if d["count"] > 0]
avg_active = round(sum(d["count"] for d in active_days) / len(active_days), 1) if active_days else 0
total_contrib = int(calendar["totalContributions"])
weekend = sum(d["count"] for d in days if d["weekday"] in (0, 6))
weekend_pct = round((weekend / total_contrib) * 100) if total_contrib else 0

recent_cutoff = today - dt.timedelta(days=28)
previous_cutoff = today - dt.timedelta(days=56)
recent_total = sum(d["count"] for d in days if dt.date.fromisoformat(d["date"]) > recent_cutoff)
previous_total = sum(
    d["count"] for d in days
    if previous_cutoff < dt.date.fromisoformat(d["date"]) <= recent_cutoff
)
if previous_total == 0:
    velocity_ratio = 1 if recent_total == 0 else None
    velocity_trend = "up" if recent_total > 0 else "neutral"
else:
    velocity_ratio = round(recent_total / previous_total, 2)
    velocity_trend = "up" if velocity_ratio >= 1.2 else "down" if velocity_ratio <= 0.8 else "neutral"

weekday_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
most_active_weekday = weekday_names[weekday_counts.index(max(weekday_counts))] if max(weekday_counts, default=0) > 0 else "—"

lang_map = {}
for repo in repos:
    lang = repo.get("primaryLanguage")
    if not lang:
        continue
    name = lang["name"]
    entry = lang_map.setdefault(name, {"name": name, "color": lang.get("color") or "#8b949e", "count": 0})
    entry["count"] += 1

lang_total = sum(v["count"] for v in lang_map.values()) or 1
languages = sorted(lang_map.values(), key=lambda x: x["count"], reverse=True)
for item in languages:
    item["percentage"] = round((item["count"] / lang_total) * 100, 1)

top_repos = sorted(repos, key=lambda r: (r["stargazerCount"], r["pushedAt"] or ""), reverse=True)[:5]

stats = {
    "generated_at": now.isoformat(),
    "window_days": 365,
    "summary": {
        "contributions": total_contrib,
        "commits": int(collection["totalCommitContributions"]),
        "pull_requests": int(collection["totalPullRequestContributions"]),
        "reviews": int(collection["totalPullRequestReviewContributions"]),
        "issues": int(collection["totalIssueContributions"]),
        "public_repos": len(repos),
        "stars": stars,
        "followers": int(user["followers"]["totalCount"]),
        "current_streak": current_streak,
        "longest_streak": longest,
        "avg_per_active_day": avg_active,
        "weekend_percentage": weekend_pct,
        "most_active_weekday": most_active_weekday,
        "velocity": {
            "trend": velocity_trend,
            "ratio": velocity_ratio,
            "recent_28d": recent_total,
            "previous_28d": previous_total
        }
    },
    "weekday_counts": [
        {"day": weekday_names[i], "count": weekday_counts[i]} for i in range(7)
    ],
    "languages": languages[:8],
    "top_repositories": [
        {
            "name": r["name"],
            "url": r["url"],
            "stars": r["stargazerCount"],
            "forks": r["forkCount"],
            "pushed_at": r["pushedAt"],
            "language": (r.get("primaryLanguage") or {}).get("name")
        } for r in top_repos
    ],
    "contribution_days": days
}
STATS_OUTPUT.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

max_count = max(day_counts.values(), default=0)
colors = ["#17110d", "#463226", "#6a4935", "#936342", "#c18458"]

def level(count):
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
    "{{PROFILE_TAGLINE}}": esc(profile["tagline"]),
    "{{PROFILE_PRINCIPLE}}": esc(profile["principle"]),
    "{{PROFILE_MODE}}": esc(profile["mode"]),
    "{{PROFILE_FOCUS}}": esc(profile["focus"]),
    "{{PROFILE_RUNTIME}}": esc(profile["runtime"]),
    "{{STACK_RUNTIME}}": esc(" · ".join(stack["runtime"])),
    "{{STACK_DISCORD}}": esc(" · ".join(stack["discord"])),
    "{{STACK_DATA}}": esc(" · ".join(stack["data"])),
    "{{STACK_OPS}}": esc(" · ".join(stack["ops"])),
    "{{STACK_WORKFLOW}}": esc(" · ".join(stack["workflow"])),
    "{{CONTRIB_TOTAL}}": str(total_contrib),
    "{{COMMITS}}": str(collection["totalCommitContributions"]),
    "{{PRS}}": str(collection["totalPullRequestContributions"]),
    "{{REPOS}}": str(len(repos)),
    "{{STARS}}": str(stars),
    "{{STREAK}}": str(longest),
    "{{UPDATED}}": now.strftime("%Y-%m-%d"),
    "{{HEATMAP}}": "\n    ".join(heatmap),
}

for i, item in enumerate(systems[:4]):
    values[f"{{{{SYS{i}_LABEL}}}}"] = esc(item["label"])
    values[f"{{{{SYS{i}_TITLE}}}}"] = esc(item["title"])
    values[f"{{{{SYS{i}_DESC}}}}"] = esc(item["description"])
    values[f"{{{{SYS{i}_STACK}}}}"] = esc(" · ".join(item["stack"]))

for i, item in enumerate(projects[:4]):
    values[f"{{{{PUB{i}_TITLE}}}}"] = esc(item["title"])
    values[f"{{{{PUB{i}_DESC}}}}"] = esc(item["description"])

svg = TEMPLATE.read_text(encoding="utf-8")
for key, value in values.items():
    svg = svg.replace(key, value)

unresolved = [token for token in set(part for part in svg.split() if "{{" in part or "}}" in part)]
if "{{" in svg or "}}" in svg:
    raise SystemExit("Unresolved template placeholders remain")

OUTPUT.write_text(svg, encoding="utf-8")
print(
    "profile stats:",
    f"contributions={total_contrib}",
    f"commits={collection['totalCommitContributions']}",
    f"prs={collection['totalPullRequestContributions']}",
    f"repos={len(repos)}",
    f"stars={stars}",
    f"current_streak={current_streak}",
    f"longest_streak={longest}",
)
