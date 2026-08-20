from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen


USERNAME = os.getenv("PROFILE_USERNAME", "Teinble")
ROOT = Path(__file__).resolve().parents[1]
PROFILE_TOKEN = os.getenv("PROFILE_TOKEN")
API_TOKEN = PROFILE_TOKEN or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")


def fetch(path: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-readme-updater"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    request = Request(f"https://api.github.com{path}", headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def graphql(query: str, variables: dict):
    if not PROFILE_TOKEN:
        raise RuntimeError("Private activity metrics require PROFILE_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {PROFILE_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "profile-readme-updater",
    }
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def collect_activity() -> dict[str, str]:
    repo_query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        id
        repositories(
          first: 100,
          after: $cursor,
          ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER],
          orderBy: {field: PUSHED_AT, direction: DESC}
        ) {
          nodes { nameWithOwner isPrivate }
          pageInfo { hasNextPage endCursor }
        }
      }
    }
    """
    repos = []
    cursor = None
    author_id = None
    while True:
        data = graphql(repo_query, {"login": USERNAME, "cursor": cursor})["user"]
        author_id = data["id"]
        connection = data["repositories"]
        repos.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]

    history_query = """
    query($owner: String!, $name: String!, $cursor: String, $author: ID!) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 100, after: $cursor, author: {id: $author}) {
                nodes { oid additions deletions committedDate }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
      }
    }
    """
    commits = {}
    for repo in repos:
        owner, name = repo["nameWithOwner"].split("/", 1)
        cursor = None
        while True:
            result = graphql(
                history_query,
                {"owner": owner, "name": name, "cursor": cursor, "author": author_id},
            )["repository"]
            branch = result and result.get("defaultBranchRef")
            if not branch:
                break
            history = branch["target"]["history"]
            for commit in history["nodes"]:
                commits.setdefault(commit["oid"], commit)
            if not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]

    additions = sum(commit["additions"] for commit in commits.values())
    deletions = sum(commit["deletions"] for commit in commits.values())
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    recent_count = sum(
        datetime.fromisoformat(commit["committedDate"].replace("Z", "+00:00")) >= cutoff
        for commit in commits.values()
    )
    private_count = sum(repo["isPrivate"] for repo in repos)
    scope = (
        f"private + public · {private_count} private repos"
        if private_count
        else "PROFILE_TOKEN connected · 0 private repos visible"
    )
    return {
        "tracked_repos": str(len(repos)),
        "commits": f"{len(commits):,}",
        "commits_per_day": f"{recent_count / 365:.2f}",
        "lines_net": f"{additions - deletions:,}",
        "lines_added": f"+{additions:,}",
        "lines_deleted": f"-{deletions:,}",
        "activity_scope": scope,
    }


def collect() -> dict[str, str]:
    user = fetch(f"/users/{USERNAME}")
    repos = fetch(f"/users/{USERNAME}/repos?per_page=100&sort=pushed")
    owned = [repo for repo in repos if not repo["fork"]]
    languages = Counter(repo["language"] for repo in owned if repo["language"])
    recent = max((repo for repo in repos if repo["name"].lower() != USERNAME.lower()), key=lambda repo: repo["pushed_at"])
    values = {
        "public_repos": str(user["public_repos"]),
        "owned_repos": str(len(owned)),
        "forks": str(len(repos) - len(owned)),
        "stars": str(sum(repo["stargazers_count"] for repo in owned)),
        "followers": str(user["followers"]),
        "following": str(user["following"]),
        "languages": " · ".join(name for name, _ in languages.most_common(4)),
        "recent_repo": recent["name"],
        "recent_date": recent["pushed_at"][:10],
    }
    if PROFILE_TOKEN:
        values.update(collect_activity())
    else:
        values["activity_scope"] = "private + public · secure sync required"
    return values


def update_svg(path: Path, values: dict[str, str]) -> None:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    tree = ET.parse(path)
    root = tree.getroot()
    for element_id, value in values.items():
        element = root.find(f".//*[@id='{element_id}']")
        if element is not None:
            element.text = value
    tree.write(path, encoding="unicode", xml_declaration=False)


def main() -> None:
    values = collect()
    for filename in ("profile-dark.svg", "profile-light.svg"):
        update_svg(ROOT / filename, values)
    print(f"Updated {USERNAME} profile at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
