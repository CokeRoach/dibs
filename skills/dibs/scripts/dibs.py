#!/usr/bin/env python3
"""dibs: is someone already working on this?

One set of facts, read from GitHub, used on both sides of a contribution:

  check   Before you start on an issue: open pull requests that already address it, people who
          said they would take it, assignees, and what the project's guides say about AI.
  pr      When a pull request arrives: does it duplicate an earlier one, or take an issue someone
          else claimed? Used by the GitHub Action; ``--dry-run`` prints instead of posting.

dibs reports facts from the issue and pull request history. It never guesses whether a person
or a model wrote something.

Standard library only. A token (GITHUB_TOKEN, GH_TOKEN, or a logged-in ``gh``) raises the API
limit from 60 to 5000 requests an hour; without one, ``check`` costs about 4 requests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

__version__ = "1.0.2"

API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
RAW = "https://raw.githubusercontent.com"
MARKER = "<!-- dibs -->"

GO, ASK, STOP = "GO", "ASK", "STOP"
EXIT = {GO: 0, ASK: 1, STOP: 2}

# Someone saying they will do the work. Questions count ("can I take this?"): the asker is
# waiting on an answer, and a second person starting meanwhile is exactly the collision.
CLAIM = re.compile(
    r"""
    \b(?:i'?d|i\s+would|i'?ll|i\s+will|i'?m\s+going\s+to|i\s+am\s+going\s+to|i\s+want\s+to|
        i\s+wish\s+to|let\s+me|can\s+i|could\s+i|may\s+i|i'?m\s+happy\s+to|i'?m\s+interested\s+in)\b
        [^.?!\n]{0,40}?
        \b(?:work(?:ing)?\s+on|take|tackl(?:e|ing)|fix(?:ing)?|handl(?:e|ing)|implement(?:ing)?|address(?:ing)?|
           grab(?:bing)?|contribut(?:e|ing)|submit(?:ting)?|open(?:ing)?|send(?:ing)?|rais(?:e|ing)|pick(?:ing)?\s+up)
        \s+(?:on\s+)?(?:this|it|that|the\s+(?:issue|fix|bug|feature|task|change)|a\s+(?:pr|pull\s+request|fix|patch))\b
  | \b(?:i'?m|i\s+am)\s+(?:already\s+|currently\s+)?working\s+on\s+(?:this|it|a\s+fix)\b
  | \bpick(?:ing)?\s+(?:this|it)\s+up\b
  | \bassign\s+(?:it\s+|this\s+)?(?:to\s+)?me\b
  | (?:^|\s)/assign\b
  | \b(?:i'?m|i\s+am)\s+on\s+it\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
# The same person later letting it go.
RELEASE = re.compile(
    r"""
    \bunassign\s+me\b
  | \b(?:can'?t|cannot|won'?t|will\s+not|no\s+longer|not\s+able\s+to)\b[^.\n]{0,30}\b(?:work\s+on|continue|finish|take|do)\b
  | \bfeel\s+free\s+to\s+(?:take|pick|work)
  | \bdropping\s+(?:this|it)\b
  | \b(?:i'?m|i\s+am)\s+not\s+working\s+on\s+(?:this|it)
  | \bsomeone\s+else\s+can\s+(?:take|pick)
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Closing keywords GitHub itself understands, and plain references.
CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*(?:([\w.-]+/[\w.-]+))?#(\d+)", re.I)
HASH_REF = re.compile(r"(?<![\w/])(?:([\w.-]+/[\w.-]+))?#(\d+)\b")
URL_REF = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/(?:issues|pull)/(\d+)")

# Words that mark a passage about AI in a project's guides. "AI" and "LLM" are matched with
# their case, so "ai" inside other words never counts.
AI_WORDS_CASED = re.compile(r"\b(?:AI|A\.I\.|LLMs?|GenAI|GPT(?:-\d+)?)\b")
AI_WORDS = re.compile(
    r"\b(?:artificial\s+intelligence|large\s+language\s+models?|generative|machine[- ]generated|"
    r"ai[- ](?:generated|assisted|written|tools?)|copilot|chatgpt|claude|gemini|cursor|"
    r"coding\s+agents?|autonomous\s+agents?|vibe[- ]cod\w*|generated[- ]by|assisted[- ]by)\b",
    re.I,
)
GUIDE_PATHS = [
    "AI_POLICY.md", ".github/AI_POLICY.md", "docs/AI_POLICY.md", "AI_CONTRIBUTING.md",
    "CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md", "CONTRIBUTING.rst",
]
TEMPLATE_PATHS = [
    ".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md",
    "PULL_REQUEST_TEMPLATE.md", "docs/pull_request_template.md",
]
STOP_LABELS = {"wontfix", "won't fix", "invalid", "duplicate", "not planned"}
ASK_LABELS = {"needs triage", "needs-triage", "triage", "needs discussion", "needs design",
              "blocked", "on hold", "awaiting decision", "question"}
WELCOME_LABELS = {"good first issue", "help wanted", "contributions welcome", "up for grabs"}
# Signals about the author rather than the work. They are never posted on the pull request: they go
# to the run's log and job summary, and the `signals` output, for maintainers who turned them on.
PRIVATE_KINDS = {"burst"}


# ---------------------------------------------------------------------------------- GitHub API

class GitHubError(RuntimeError):
    pass


def find_token() -> str | None:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    gh = shutil.which("gh")
    if gh:
        try:
            out = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


class GitHub:
    def __init__(self, token: str | None = None):
        self.token = token
        self.calls = 0

    def request(self, method: str, url: str, body: dict | None = None):
        if not url.startswith("http"):
            url = API + url
        headers = {"Accept": "application/vnd.github+json", "User-Agent": f"dibs/{__version__}",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return (json.loads(raw) if raw else None), resp.headers
        except urllib.error.HTTPError as err:
            if err.code in (403, 429) and err.headers.get("X-RateLimit-Remaining") == "0":
                reset = dt.datetime.fromtimestamp(int(err.headers.get("X-RateLimit-Reset", "0")))
                hint = "" if self.token else (" Without a token GitHub allows 60 requests an hour; set GITHUB_TOKEN "
                                              "or run `gh auth login`.")
                raise GitHubError(f"GitHub API rate limit reached; it resets at {reset:%H:%M}.{hint}") from None
            if err.code == 404:
                raise GitHubError(f"not found: {url}") from None
            detail = err.read().decode(errors="replace")[:300]
            raise GitHubError(f"GitHub API {err.code} for {method} {url}: {detail}") from None
        except urllib.error.URLError as err:
            raise GitHubError(f"could not reach GitHub: {err.reason}") from None

    def get(self, path: str, params: dict | None = None):
        url = path + ("?" + urllib.parse.urlencode(params) if params else "")
        return self.request("GET", url)[0]

    def paged(self, path: str, params: dict | None = None, limit: int = 500) -> list:
        params = dict(params or {}, per_page=100)
        url = path + "?" + urllib.parse.urlencode(params)
        items: list = []
        while url and len(items) < limit:
            data, headers = self.request("GET", url)
            items.extend(data if isinstance(data, list) else data.get("items", []))
            url = _next_link(headers.get("Link", ""))
        return items[:limit]

    def raw(self, repo: str, path: str) -> str | None:
        """A file from the default branch, without spending API quota."""
        url = f"{RAW}/{repo}/HEAD/{urllib.parse.quote(path)}"
        req = urllib.request.Request(url, headers={"User-Agent": f"dibs/{__version__}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError):
            return None


def _next_link(link: str) -> str | None:
    for part in link.split(","):
        if 'rel="next"' in part:
            return part[part.index("<") + 1:part.index(">")]
    return None


# --------------------------------------------------------------------------------------- facts

def parse_time(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def now() -> dt.datetime:
    fixed = os.environ.get("DIBS_NOW")  # tests pin the clock
    return parse_time(fixed) if fixed else dt.datetime.now(dt.timezone.utc)


def days_between(a: dt.datetime, b: dt.datetime) -> float:
    return abs((b - a).total_seconds()) / 86400


def is_bot(user: dict | None) -> bool:
    if not user:
        return True
    return user.get("type") == "Bot" or user.get("login", "").endswith("[bot]")


def readable(text: str | None) -> str:
    """Comment text as people read it: no HTML comments (templates hide example lines there) or quotes."""
    text = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def strip_noise(text: str | None) -> str:
    """``readable`` text without code, so names in code (``.claude/``, ``fix_it()``) never match a phrase."""
    text = re.sub(r"```.*?```", "", readable(text), flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def snippet(text: str, width: int = 140) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= width else flat[:width - 1].rstrip() + "…"


@dataclass
class Claim:
    login: str
    at: str
    text: str
    url: str
    released: bool = False


@dataclass
class LinkedPR:
    number: int
    login: str
    state: str          # open, closed or merged
    draft: bool
    created_at: str
    title: str
    url: str
    repo: str


@dataclass
class IssueFacts:
    repo: str
    number: int
    title: str
    state: str
    author: str
    url: str
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    prs: list[LinkedPR] = field(default_factory=list)


def find_claims(comments: list[dict]) -> list[Claim]:
    """Claims in comment order; a later release by the same person marks their claim released."""
    claims: list[Claim] = []
    for c in comments:
        if is_bot(c.get("user")):
            continue
        login = c["user"]["login"]
        body = strip_noise(c.get("body"))
        if RELEASE.search(body):
            for claim in claims:
                if claim.login == login:
                    claim.released = True
            continue
        m = CLAIM.search(body)
        if m:
            claims.append(Claim(login, c["created_at"], snippet(readable(c.get("body"))), c.get("html_url", "")))
    return claims


def linked_prs(timeline: list[dict], repo: str) -> list[LinkedPR]:
    """Pull requests that mention the issue, from its timeline's cross-reference events."""
    seen: dict[str, LinkedPR] = {}
    for event in timeline:
        if event.get("event") != "cross-referenced":
            continue
        src = (event.get("source") or {}).get("issue") or {}
        if "pull_request" not in src:
            continue
        src_repo = src.get("repository", {}).get("full_name") or _repo_from_url(src.get("html_url", "")) or repo
        merged = bool((src.get("pull_request") or {}).get("merged_at"))
        state = "merged" if merged else src.get("state", "open")
        key = f"{src_repo}#{src['number']}"
        seen[key] = LinkedPR(src["number"], (src.get("user") or {}).get("login", "?"), state,
                             bool(src.get("draft")), src.get("created_at", ""), src.get("title", ""),
                             src.get("html_url", ""), src_repo)
    return sorted(seen.values(), key=lambda p: p.created_at)


def _repo_from_url(url: str) -> str | None:
    m = re.match(r"https://github\.com/([\w.-]+/[\w.-]+)/", url)
    return m.group(1) if m else None


def issue_facts(gh: GitHub, repo: str, number: int) -> IssueFacts:
    issue = gh.get(f"/repos/{repo}/issues/{number}")
    if "pull_request" in issue:
        raise GitHubError(f"{repo}#{number} is a pull request, not an issue")
    comments = gh.paged(f"/repos/{repo}/issues/{number}/comments", limit=300) if issue.get("comments") else []
    timeline = gh.paged(f"/repos/{repo}/issues/{number}/timeline", limit=500)
    return IssueFacts(
        repo=repo, number=number, title=issue.get("title", ""), state=issue.get("state", "open"),
        author=(issue.get("user") or {}).get("login", "?"), url=issue.get("html_url", ""),
        labels=[l["name"] for l in issue.get("labels", [])],
        assignees=[a["login"] for a in issue.get("assignees", [])],
        claims=find_claims(comments), prs=linked_prs(timeline, repo),
    )


def ai_passages(text: str, limit: int = 6) -> list[dict]:
    """Passages of a guide that talk about AI: whole sections whose heading does, else paragraphs."""
    lines = text.splitlines()
    out: list[dict] = []
    heading = ""
    i = 0
    while i < len(lines) and len(out) < limit:
        line = lines[i]
        h = re.match(r"^(#{1,6})\s+(.*)", line)
        if h:
            heading = h.group(2).strip()
            if _mentions_ai(heading):
                level = len(h.group(1))
                j = i + 1
                while j < len(lines) and not re.match(rf"^#{{1,{level}}}\s", lines[j]):
                    j += 1
                body = "\n".join(lines[i + 1:j]).strip()
                out.append({"heading": heading, "line": i + 1, "text": _trim(body, 1500)})
                i = j
                continue
        if line.strip() and _mentions_ai(line):
            j = i
            while j > 0 and lines[j - 1].strip() and not lines[j - 1].startswith("#"):
                j -= 1
            k = i
            while k + 1 < len(lines) and lines[k + 1].strip() and not lines[k + 1].startswith("#"):
                k += 1
            out.append({"heading": heading, "line": j + 1, "text": _trim("\n".join(lines[j:k + 1]), 700)})
            i = k + 1
            continue
        i += 1
    return out


def _mentions_ai(text: str) -> bool:
    text = re.sub(r"`[^`\n]*`", "", text)  # a path like `.claude/skills/` is not a passage about AI
    return bool(AI_WORDS_CASED.search(text) or AI_WORDS.search(text))


def _trim(text: str, width: int) -> str:
    text = text.strip()
    return text if len(text) <= width else text[:width].rstrip() + " …"


def project_guides(gh: GitHub, repo: str) -> dict:
    guides = []
    for path in GUIDE_PATHS:
        text = gh.raw(repo, path)
        if text:
            guides.append({"path": path, "url": f"https://github.com/{repo}/blob/HEAD/{path}",
                           "ai": ai_passages(text)})
    template = next((p for p in TEMPLATE_PATHS if gh.raw(repo, p)), None)
    return {"guides": guides, "pr_template": template}


# ------------------------------------------------------------------------------------ verdicts

def check_verdict(facts: IssueFacts, me: str | None, claim_days: float, at: dt.datetime) -> tuple[str, list[str], list[str]]:
    """(verdict, reasons to stop or ask, notes) for someone about to start on the issue."""
    stop: list[str] = []
    ask: list[str] = []
    notes: list[str] = []
    others = lambda login: (me is None) or (login.lower() != me.lower())  # noqa: E731

    if facts.state != "open":
        stop.append(f"the issue is {facts.state}")
    for pr in facts.prs:
        if pr.repo.lower() != facts.repo.lower():
            notes.append(f"{pr.repo}#{pr.number} in another repository mentions this issue ({pr.state})")
            continue
        if pr.state == "open" and others(pr.login):
            kind = "draft PR" if pr.draft else "open PR"
            stop.append(f"{kind} #{pr.number} by {pr.login} ({pr.created_at[:10]}): {pr.title}")
        elif pr.state == "merged":
            ask.append(f"PR #{pr.number} by {pr.login} was merged and mentions this issue; check whether "
                       f"anything is left to do: {pr.title}")
        elif pr.state == "closed" and others(pr.login):
            ask.append(f"PR #{pr.number} by {pr.login} was closed without merging; read why first: {pr.url}")
    for login in facts.assignees:
        if others(login):
            stop.append(f"assigned to {login}")
    open_pr_authors = {p.login for p in facts.prs if p.state == "open" and p.repo.lower() == facts.repo.lower()}
    ended = finished_claimants(facts, facts.repo)
    for claim in facts.claims:
        if not others(claim.login) or claim.released or claim.login in ended:
            continue
        age = days_between(parse_time(claim.at), at)
        if age <= claim_days or claim.login in open_pr_authors:
            stop.append(f"{claim.login} said they would take it {age:.0f} days ago: \"{claim.text}\"")
        else:
            ask.append(f"{claim.login} claimed it {age:.0f} days ago and has not opened a PR; ask before starting: \"{claim.text}\"")
    labels = {l.lower() for l in facts.labels}
    for label in sorted(labels & STOP_LABELS):
        stop.append(f"labelled \"{label}\"")
    for label in sorted(labels & ASK_LABELS):
        ask.append(f"labelled \"{label}\": a maintainer has not settled the approach yet")
    verdict = STOP if stop else ASK if ask else GO
    if labels & WELCOME_LABELS:
        note = "maintainers marked this open for contributors: " + ", ".join(sorted(labels & WELCOME_LABELS))
        if verdict != GO:
            note += " (such labels often stay on after someone has taken the issue)"
        notes.append(note)
    # Under STOP, the ASK reasons still help: a PR closed as a duplicate says how the maintainers decide.
    return verdict, stop + ask, notes


def finished_claimants(facts: IssueFacts, repo: str) -> set[str]:
    """People whose own pull request for the issue was closed or merged, with none still open.

    Their claim ended with that pull request, which is reported on its own; counting the claim as
    well would say they are still on it."""
    here = [p for p in facts.prs if p.repo.lower() == repo.lower()]
    return {p.login for p in here if p.state in ("closed", "merged")} - {p.login for p in here if p.state == "open"}


@dataclass
class Signal:
    kind: str           # duplicate, claimed, assigned, already-fixed, burst, disclosure
    text: str


def pr_signals(gh: GitHub, repo: str, pr: dict, claim_days: float, burst_threshold: int,
               disclosure: str | None) -> tuple[list[Signal], list[int]]:
    """Facts a maintainer wants before reviewing ``pr``; also the issue numbers it refers to."""
    author = pr["user"]["login"]
    created = parse_time(pr["created_at"])
    issues = referenced_issues(pr.get("title", ""), pr.get("body"), repo)
    signals: list[Signal] = []
    checked: list[int] = []
    for number in issues:
        try:
            facts = issue_facts(gh, repo, number)
        except GitHubError as err:
            if "is a pull request" in str(err) or "not found" in str(err):
                continue
            raise
        checked.append(number)
        for other in facts.prs:
            if other.repo.lower() != repo.lower() or other.number == pr["number"]:
                continue
            if other.state == "merged":
                signals.append(Signal("already-fixed", f"#{number} was already addressed by #{other.number} "
                                      f"(`{other.login}`, merged): {other.title}"))
            elif other.state == "open" and other.login != author and parse_time(other.created_at) < created:
                signals.append(Signal("duplicate", f"#{other.number} by `{other.login}` also refers to #{number} and was "
                                      f"opened {_ago(parse_time(other.created_at), created)} earlier: {other.title}"))
        for login in facts.assignees:
            if login != author:
                signals.append(Signal("assigned", f"#{number} is assigned to `{login}`."))
        open_pr_authors = {p.login for p in facts.prs if p.state == "open"}
        ended = finished_claimants(facts, repo)
        for claim in facts.claims:
            claimed = parse_time(claim.at)
            if claim.login == author or claim.released or claimed > created or claim.login in ended:
                continue
            if days_between(claimed, created) <= claim_days or claim.login in open_pr_authors:
                signals.append(Signal("claimed", f"`{claim.login}` said they would take #{number} "
                                      f"{_ago(claimed, created)} before this PR: \"{claim.text}\""))
    if burst_threshold > 0:
        # The day before this PR, not before now, so a later run on the same PR finds the same count.
        window = f"{created - dt.timedelta(hours=24):%Y-%m-%dT%H:%M:%SZ}..{created:%Y-%m-%dT%H:%M:%SZ}"
        try:
            found = gh.get("/search/issues", {"q": f"type:pr author:{author} created:{window}", "per_page": 100})
        except GitHubError as err:
            # An optional note: losing it must not lose the overlap found above. Search has its own,
            # smaller rate limit.
            print(f"dibs: skipped the burst note: {err}", file=sys.stderr)
            found = {}
        items = found.get("items", [])
        # Only other repositories count: a change split into several small PRs to one project is
        # good practice, not a burst.
        elsewhere = {i.get("repository_url", "").rsplit("/repos/", 1)[-1].lower() for i in items} - {repo.lower()}
        if len(elsewhere) >= burst_threshold:
            total = found.get("total_count", 0)
            more = "at least " if total > len(items) else ""
            signals.append(Signal("burst", f"`{author}` opened {total} pull requests in the 24 hours up to and "
                                  f"including this one, in {more}{len(elsewhere)} other repositories."))
    if disclosure and not re.search(disclosure, pr.get("body") or "", re.I | re.M):
        signals.append(Signal("disclosure", "The description has no AI-use disclosure line, which this "
                              "project's contributing guide asks for."))
    return signals, checked


def referenced_issues(title: str, body: str | None, repo: str) -> list[int]:
    """Issue numbers in this repository that the title or description refers to, closing ones first."""
    text = strip_noise((title or "") + "\n" + (body or ""))
    ordered: list[int] = []

    def add(r: str | None, n: str):
        if (r is None or r.lower() == repo.lower()) and int(n) not in ordered:
            ordered.append(int(n))

    for m in CLOSING.finditer(text):
        add(m.group(1), m.group(2))
    for m in URL_REF.finditer(text):
        add(m.group(1), m.group(2))
    for m in HASH_REF.finditer(text):
        add(m.group(1), m.group(2))
    return ordered[:10]


def _ago(a: dt.datetime, b: dt.datetime) -> str:
    hours = abs((b - a).total_seconds()) / 3600
    if hours < 1:
        return "less than an hour"
    if hours < 48:
        return f"{hours:.0f} hours"
    return f"{hours / 24:.0f} days"


def render_comment(signals: list[Signal], pr_number: int) -> str:
    lines = [MARKER, "Thanks for the pull request. Before review, here is some overlap a maintainer will want to know about:", ""]
    titles = {"duplicate": "Earlier pull request", "claimed": "Claimed issue", "assigned": "Assigned issue",
              "already-fixed": "Already fixed", "burst": "Pull requests in many repositories", "disclosure": "AI-use disclosure"}
    for s in signals:
        lines.append(f"- **{titles.get(s.kind, s.kind)}:** {s.text}")
    lines += ["", "If this PR takes a different approach, say how in the description. If it overlaps, consider "
              "reviewing or testing the earlier work instead.", "",
              "<sub>Checked by [dibs](https://github.com/CokeRoach/dibs) from the issue and pull request history. "
              "It does not judge the code or guess who wrote it.</sub>"]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------- commands

def parse_target(text: str) -> tuple[str, int]:
    m = URL_REF.match(text) or re.match(r"^([\w.-]+/[\w.-]+)#(\d+)$", text.strip())
    if not m:
        raise ValueError(f"expected an issue URL or owner/repo#number, got {text!r}")
    return m.group(1), int(m.group(2))


def cmd_check(args) -> int:
    repo, number = parse_target(args.issue)
    gh = GitHub(find_token())
    me = args.me
    if me is None and gh.token:
        try:
            me = gh.get("/user").get("login")
        except GitHubError:
            me = None
    facts = issue_facts(gh, repo, number)
    verdict, reasons, notes = check_verdict(facts, me, args.claim_days, now())
    guides = project_guides(gh, repo)
    if args.json:
        print(json.dumps({"verdict": verdict, "reasons": reasons, "notes": notes, "issue": asdict(facts),
                          "guides": guides, "api_calls": gh.calls}, indent=2, ensure_ascii=False))
        return EXIT[verdict]
    print(f"dibs: {repo}#{number} \"{facts.title}\" ({facts.state})\n{facts.url}\n")
    headline = {GO: "GO    nobody else is on this", ASK: "ASK   check with the maintainers or the claimant first",
                STOP: "STOP  someone is already on this, or it is settled"}[verdict]
    print(headline)
    for r in reasons:
        print(f"  - {r}")
    for n in notes:
        print(f"  · {n}")
    print("\nRead before contributing")
    if not guides["guides"]:
        print("  - no CONTRIBUTING or AI policy file found at the usual paths; check the README")
    for g in guides["guides"]:
        print(f"  - {g['path']}  {g['url']}")
        for p in g["ai"]:
            where = f" › {p['heading']}" if p["heading"] else ""
            print(f"      line {p['line']}{where}:")
            for line in p["text"].splitlines()[:12]:
                print(f"        {line}")
    if guides["pr_template"]:
        print(f"  - pull request template: {guides['pr_template']}")
    print(f"\n({gh.calls} API requests{'' if gh.token else ', no token'})")
    return EXIT[verdict]


def cmd_pr(args) -> int:
    """Used by the GitHub Action (event from GITHUB_EVENT_PATH) or by hand with --repo and --number."""
    gh = GitHub(args.token or find_token())
    if args.repo and args.number:
        repo, pr = args.repo, gh.get(f"/repos/{args.repo}/pulls/{args.number}")
    else:
        if not os.environ.get("GITHUB_EVENT_PATH"):
            raise ValueError("no pull request given: pass --repo and --number, or run it from a GitHub Action")
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            event = json.load(f)
        if "pull_request" not in event:
            raise ValueError("this workflow event has no pull request; run dibs on pull_request_target")
        pr, repo = event["pull_request"], event["repository"]["full_name"]
    exempt = {a.strip().upper() for a in args.exempt.split(",") if a.strip()}
    if pr.get("author_association", "").upper() in exempt or is_bot(pr.get("user")):
        print(f"dibs: skipped, {pr['user']['login']} is {pr.get('author_association')} here")
        _set_output("signals", "")
        return 0
    signals, issues = pr_signals(gh, repo, pr, args.claim_days, args.burst, args.disclosure or None)
    kinds = sorted({s.kind for s in signals})
    _set_output("signals", ",".join(kinds))
    public = [s for s in signals if s.kind not in PRIVATE_KINDS]
    private = [s for s in signals if s.kind in PRIVATE_KINDS]
    body = render_comment(public, pr["number"]) if public else ""
    _write_summary(repo, pr["number"], public, private)
    for s in private:
        print(f"dibs: for maintainers, not posted on the pull request: {s.text.replace('`', '')}")
    if args.dry_run:
        print(f"dibs: {repo}#{pr['number']} refers to issues {issues or 'none'}; signals: {kinds or 'none'}")
        if body:
            print("\n" + body)
        return 0
    try:
        if args.comment:
            _sync_comment(gh, repo, pr["number"], body)
        if args.labels:
            _sync_labels(gh, repo, pr["number"], sorted({s.kind for s in public}),
                         [l["name"] for l in pr.get("labels", [])])
    except GitHubError as err:
        # Usually a read-only token: the `pull_request` event gives one for pull requests from forks.
        print(f"::warning title=dibs could not write to the pull request::{err}. Run dibs on "
              "pull_request_target with issues and pull-requests write permission (see the README).")
        if body:
            print("\n" + body)
    fail = {k.strip() for k in args.fail_on.split(",") if k.strip()}
    if fail & set(kinds):
        print(f"dibs: failing on {', '.join(sorted(fail & set(kinds)))}")
        return 1
    print(f"dibs: {repo}#{pr['number']}: {', '.join(kinds) or 'no overlap found'}")
    return 0


def _sync_comment(gh: GitHub, repo: str, number: int, body: str) -> None:
    mine = [c for c in gh.paged(f"/repos/{repo}/issues/{number}/comments", limit=300)
            if MARKER in (c.get("body") or "") and is_bot(c.get("user"))]
    if mine and body:
        gh.request("PATCH", f"/repos/{repo}/issues/comments/{mine[0]['id']}", {"body": body})
    elif mine:
        gh.request("PATCH", f"/repos/{repo}/issues/comments/{mine[0]['id']}",
                   {"body": MARKER + "\nThe overlap dibs found earlier is gone. Thanks!"})
    elif body:
        gh.request("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})


def _sync_labels(gh: GitHub, repo: str, number: int, kinds: list[str], current: list[str]) -> None:
    wanted = {f"dibs: {k}" for k in kinds}
    have = {l for l in current if l.startswith("dibs: ")}
    if wanted - have:
        gh.request("POST", f"/repos/{repo}/issues/{number}/labels", {"labels": sorted(wanted - have)})
    for label in have - wanted:
        gh.request("DELETE", f"/repos/{repo}/issues/{number}/labels/{urllib.parse.quote(label)}")


def _write_summary(repo: str, number: int, public: list[Signal], private: list[Signal]) -> None:
    """The job summary on the workflow run's page, which maintainers read and the PR does not show."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [f"### dibs: {repo}#{number}", ""]
    titles = {"duplicate": "Earlier pull request", "claimed": "Claimed issue", "assigned": "Assigned issue",
              "already-fixed": "Already fixed", "disclosure": "AI-use disclosure", "burst": "Pull requests in many repositories"}
    for s in public:
        lines.append(f"- **{titles.get(s.kind, s.kind)}:** {s.text}")
    for s in private:
        lines.append(f"- **{titles.get(s.kind, s.kind)}** (not posted on the pull request): {s.text}")
    if not public and not private:
        lines.append("No overlap with earlier work found.")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _set_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="dibs", description=__doc__.split("\n\n")[0])
    ap.add_argument("--version", action="version", version=f"dibs {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="before starting on an issue: is someone already on it?")
    c.add_argument("issue", help="issue URL or owner/repo#number")
    c.add_argument("--me", help="your GitHub login, so your own claims and PRs are not counted (read from the token if left out)")
    c.add_argument("--claim-days", type=float, default=21, help="a claim older than this, with no PR, is stale (default 21)")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_check)

    p = sub.add_parser("pr", help="for maintainers: does this pull request overlap earlier work?")
    p.add_argument("--repo", help="owner/repo, with --number, to check any pull request by hand")
    p.add_argument("--number", type=int)
    p.add_argument("--token", default=os.environ.get("INPUT_TOKEN"))
    p.add_argument("--claim-days", type=float, default=float(os.environ.get("INPUT_CLAIM_DAYS") or 21))
    p.add_argument("--burst", type=int, default=int(os.environ.get("INPUT_BURST_THRESHOLD") or 0),
                   help="note, for maintainers only, authors who opened PRs in at least this many other "
                        "repositories in the 24 hours up to this one (default 0 = off)")
    p.add_argument("--disclosure", default=os.environ.get("INPUT_REQUIRE_DISCLOSURE", ""),
                   help="regular expression the description must contain, e.g. 'Assisted-by:|Generated-by:'")
    p.add_argument("--exempt", default=os.environ.get("INPUT_EXEMPT_ASSOCIATIONS") or "OWNER,MEMBER,COLLABORATOR")
    p.add_argument("--fail-on", default=os.environ.get("INPUT_FAIL_ON", ""))
    p.add_argument("--no-comment", dest="comment", action="store_false",
                   default=os.environ.get("INPUT_COMMENT", "true").lower() != "false")
    p.add_argument("--no-labels", dest="labels", action="store_false",
                   default=os.environ.get("INPUT_LABELS", "true").lower() != "false")
    p.add_argument("--dry-run", action="store_true", help="print what would be posted")
    p.set_defaults(func=cmd_pr)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (GitHubError, ValueError, KeyError) as err:
        print(f"dibs: {err}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
