import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "dibs" / "scripts" / "dibs.py"
spec = importlib.util.spec_from_file_location("dibs", SCRIPT)
dibs = importlib.util.module_from_spec(spec)
sys.modules["dibs"] = dibs
spec.loader.exec_module(dibs)

REPO = "acme/widget"
NOW = "2026-11-25T12:00:00Z"


def user(login, kind="User"):
    return {"login": login, "type": kind}


def comment(login, body, at, kind="User"):
    return {"user": user(login, kind), "body": body, "created_at": at, "html_url": f"https://github.com/{REPO}/issues/1#c"}


def xref(number, login, at, state="open", merged=False, draft=False, repo=REPO, title="a fix"):
    pr = {"merged_at": "2026-11-20T00:00:00Z" if merged else None}
    return {"event": "cross-referenced", "source": {"issue": {
        "number": number, "user": user(login), "state": "closed" if merged else state, "draft": draft,
        "created_at": at, "title": title, "html_url": f"https://github.com/{repo}/pull/{number}",
        "repository": {"full_name": repo}, "pull_request": pr}}}


class FakeGitHub:
    """Canned GitHub: ``data`` maps an API path to its JSON; writes are recorded."""

    def __init__(self, data, raw=None):
        self.data, self.raw_files, self.sent, self.calls, self.token = data, raw or {}, [], 0, "t"
        self.queries = []

    def get(self, path, params=None):
        self.calls += 1
        self.queries.append((path, params))
        if path not in self.data:
            raise dibs.GitHubError(f"not found: {path}")
        return self.data[path]

    def paged(self, path, params=None, limit=500):
        return list(self.get(path))[:limit]

    def raw(self, repo, path):
        return self.raw_files.get(path)

    def request(self, method, url, body=None):
        self.sent.append((method, url, body))
        return None, {}


def issue(number=1, state="open", assignees=(), labels=(), comments=1):
    return {"number": number, "title": "Crash on start", "state": state, "user": user("reporter"),
            "html_url": f"https://github.com/{REPO}/issues/{number}", "comments": comments,
            "assignees": [user(a) for a in assignees], "labels": [{"name": l} for l in labels]}


def facts_for(comments=(), timeline=(), **kw):
    gh = FakeGitHub({f"/repos/{REPO}/issues/1": issue(**kw),
                     f"/repos/{REPO}/issues/1/comments": list(comments),
                     f"/repos/{REPO}/issues/1/timeline": list(timeline)})
    return dibs.issue_facts(gh, REPO, 1)


def verdict(facts, me=None, days=21):
    return dibs.check_verdict(facts, me, days, dibs.parse_time(NOW))


def test_stop_also_lists_what_would_ask_and_doubts_stale_welcome_labels():
    facts = facts_for(labels=["good first issue"], timeline=[
        xref(5, "alice", "2026-11-20T00:00:00Z"),
        xref(6, "bob", "2026-11-21T00:00:00Z", state="closed")])
    v, reasons, notes = verdict(facts)
    assert v == dibs.STOP
    assert "open PR #5 by alice" in reasons[0] and "PR #6 by bob was closed without merging" in reasons[1]
    assert "often stay on" in notes[0]


# ----------------------------------------------------------------------------- claim phrases

@pytest.mark.parametrize("text", [
    "I'd like to take this. Approach: make the renderer handle bold.",
    "Picking this up — renderMarkdown grows an inline pass",
    "Hi, I'd like to work on this one — I'll add the warnings",
    "Can I work on this?", "/assign", "Please assign me", "I'll open a PR tonight",
    "I'm working on it", "I'm happy to take this on", "Could I tackle this issue?",
])
def test_claims(text):
    assert dibs.CLAIM.search(dibs.strip_noise(text))


@pytest.mark.parametrize("text", [
    "I can reproduce this; the fix is probably in docs.ts",
    "let me take a look at the logs",
    "Thanks! This would fix my problem too.",
    "> I'd like to take this\nSure, go ahead!",
    "Opened a pull request for this: https://github.com/x/y/pull/1",
    "Run `I'd like to take this` as a test string",
])
def test_not_claims(text):
    assert not dibs.CLAIM.search(dibs.strip_noise(text))


@pytest.mark.parametrize("text, released", [
    ("Sorry, I can't continue on this, feel free to take it", True),
    ("I won't be able to finish this", True),
    ("This won't fix the root cause", False),
])
def test_release(text, released):
    assert bool(dibs.RELEASE.search(text)) == released


# -------------------------------------------------------------------------------- references

def test_references_ignore_template_examples_and_other_repos():
    body = 'Fixes #12\n<!-- use "Fixes #123" -->\nSee https://github.com/acme/widget/issues/14 and other/repo#5\n```\n#99\n```'
    assert dibs.referenced_issues("fix: crash (#13)", body, REPO) == [12, 14, 13]


def test_timeline_prs_states_and_repos():
    prs = dibs.linked_prs([xref(5, "a", "2026-11-01T00:00:00Z"), xref(6, "b", "2026-11-02T00:00:00Z", merged=True),
                           xref(7, "c", "2026-11-03T00:00:00Z", state="closed"),
                           xref(8, "d", "2026-11-04T00:00:00Z", repo="fork/widget"),
                           {"event": "labeled"}], REPO)
    assert [(p.number, p.state, p.repo) for p in prs] == [(5, "open", REPO), (6, "merged", REPO),
                                                           (7, "closed", REPO), (8, "open", "fork/widget")]


# ---------------------------------------------------------------------------------- verdicts

def test_nobody_on_it_is_go():
    v, reasons, notes = verdict(facts_for(labels=["good first issue"]))
    assert v == dibs.GO and not reasons and "good first issue" in notes[0]


def test_open_pr_by_someone_else_stops():
    v, reasons, _ = verdict(facts_for(timeline=[xref(5, "alice", "2026-11-20T00:00:00Z", draft=True)]))
    assert v == dibs.STOP and "draft PR #5 by alice" in reasons[0]


def test_my_own_claim_and_pr_do_not_stop_me():
    f = facts_for(comments=[comment("me", "I'll take this", "2026-11-24T00:00:00Z")],
                  timeline=[xref(5, "me", "2026-11-24T10:00:00Z")])
    assert verdict(f, me="me")[0] == dibs.GO


def test_recent_claim_stops_and_old_claim_asks():
    recent = facts_for(comments=[comment("bob", "Can I work on this?", "2026-11-20T00:00:00Z")])
    old = facts_for(comments=[comment("bob", "Can I work on this?", "2026-09-01T00:00:00Z")])
    assert verdict(recent)[0] == dibs.STOP
    v, reasons, _ = verdict(old)
    assert v == dibs.ASK and "has not opened a PR" in reasons[0]


def test_old_claim_with_an_open_pr_still_stops():
    f = facts_for(comments=[comment("bob", "I'll take this", "2026-09-01T00:00:00Z")],
                  timeline=[xref(9, "bob", "2026-09-02T00:00:00Z")])
    assert verdict(f)[0] == dibs.STOP


def test_released_claim_does_not_count():
    f = facts_for(comments=[comment("bob", "I'll take this", "2026-11-20T00:00:00Z"),
                            comment("bob", "Sorry, I can't continue, feel free to take it", "2026-11-22T00:00:00Z")])
    assert verdict(f)[0] == dibs.GO


def test_bots_never_claim():
    f = facts_for(comments=[comment("helper[bot]", "I'll take this", "2026-11-24T00:00:00Z", kind="Bot")])
    assert verdict(f)[0] == dibs.GO


@pytest.mark.parametrize("kw, expected", [
    ({"state": "closed"}, dibs.STOP),
    ({"assignees": ["carol"]}, dibs.STOP),
    ({"labels": ["wontfix"]}, dibs.STOP),
    ({"labels": ["needs triage"]}, dibs.ASK),
])
def test_issue_state_labels_and_assignees(kw, expected):
    assert verdict(facts_for(**kw))[0] == expected


def test_merged_pr_asks_and_closed_pr_asks():
    merged = facts_for(timeline=[xref(6, "b", "2026-11-02T00:00:00Z", merged=True)])
    closed = facts_for(timeline=[xref(7, "c", "2026-11-03T00:00:00Z", state="closed")])
    assert verdict(merged)[0] == dibs.ASK
    assert verdict(closed)[0] == dibs.ASK


def test_pr_in_another_repository_is_only_a_note():
    v, reasons, notes = verdict(facts_for(timeline=[xref(8, "d", "2026-11-04T00:00:00Z", repo="fork/widget")]))
    assert v == dibs.GO and "fork/widget#8" in notes[0]


# ----------------------------------------------------------------------------- AI passages

def test_ai_policy_section_is_found_but_code_paths_are_not():
    guide = ("# Contributing\n\nSkills live in `.claude/skills/`.\n\n"
             "## AI-assisted contributions\n\nDisclose AI use with an `Assisted-by:` line.\nYou must understand the code.\n\n"
             "## Tests\n\nRun pytest.\n\nWe do not accept PRs written by an LLM without review.\n")
    found = dibs.ai_passages(guide)
    assert [p["heading"] for p in found] == ["AI-assisted contributions", "Tests"]
    assert "Assisted-by" in found[0]["text"] and "Run pytest" not in found[0]["text"]
    assert "LLM" in found[1]["text"]


# -------------------------------------------------------------------------------- PR signals

def pr(number=20, login="newbie", at="2026-11-24T00:00:00Z", body="Fixes #1", association="NONE"):
    return {"number": number, "user": user(login), "created_at": at, "title": "fix crash", "body": body,
            "author_association": association, "labels": []}


def pr_gh(comments=(), timeline=(), search_total=0, repos=7, **kw):
    """``search_total`` PRs by the author spread over ``repos`` other repositories (0 = all in REPO)."""
    where = (lambda i: f"o/r{i % repos}") if repos else (lambda i: REPO)
    return FakeGitHub({f"/repos/{REPO}/issues/1": issue(**kw),
                       f"/repos/{REPO}/issues/1/comments": list(comments),
                       f"/repos/{REPO}/issues/1/timeline": list(timeline),
                       "/search/issues": {"total_count": search_total,
                                          "items": [{"repository_url": f"https://api.github.com/repos/{where(i)}"}
                                                    for i in range(min(search_total, 100))]}})


def signals(gh, the_pr, disclosure=None, burst=0):
    found, _ = dibs.pr_signals(gh, REPO, the_pr, 21, burst, disclosure)
    return found


def test_earlier_open_pr_is_a_duplicate_and_later_one_is_not():
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z"), xref(25, "zed", "2026-11-24T05:00:00Z"),
                         xref(20, "newbie", "2026-11-24T00:00:00Z")])
    found = signals(gh, pr())
    assert [s.kind for s in found] == ["duplicate"]
    assert "#15 by `alice`" in found[0].text and "2 days earlier" in found[0].text


def test_claims_before_the_pr_count_and_after_do_not():
    gh = pr_gh(comments=[comment("bob", "I'd like to work on this", "2026-11-23T00:00:00Z"),
                         comment("carl", "Can I take this?", "2026-11-24T06:00:00Z"),
                         comment("newbie", "I'll take this", "2026-11-23T12:00:00Z")])
    found = signals(gh, pr())
    assert [(s.kind, s.text.split("`")[1]) for s in found] == [("claimed", "bob")]


def test_already_fixed_assigned_burst_and_disclosure():
    gh = pr_gh(timeline=[xref(9, "dora", "2026-11-01T00:00:00Z", merged=True)], assignees=["erin"], search_total=37)
    kinds = [s.kind for s in signals(gh, pr(body="Fixes #1"), disclosure=r"^Assisted-by:", burst=5)]
    assert kinds == ["already-fixed", "assigned", "burst", "disclosure"]
    assert signals(gh, pr(body="Fixes #1\nAssisted-by: Claude"), disclosure=r"^Assisted-by:")[-1].kind != "disclosure"


def test_burst_counts_other_repositories_in_the_day_before_the_pr():
    gh = pr_gh(search_total=12)
    found = signals(gh, pr(at="2026-11-20T08:00:00Z"), burst=5)
    query = next(params["q"] for path, params in gh.queries if path == "/search/issues")
    assert "created:2026-11-19T08:00:00Z..2026-11-20T08:00:00Z" in query  # not "before now"
    assert [s.kind for s in found] == ["burst"]
    assert "12 pull requests in the 24 hours up to and including this one, in 7 other repositories" in found[0].text
    assert signals(gh, pr(), burst=8) == []


def test_a_claim_ends_when_the_claimants_own_pr_is_closed():
    f = facts_for(comments=[comment("bob", "I'd like to work on this", "2026-11-23T00:00:00Z")],
                  timeline=[xref(6, "bob", "2026-11-23T05:00:00Z", state="closed")])
    v, reasons, _ = verdict(f)
    assert v == dibs.ASK  # the closed PR still says: read why it was closed
    assert not any("said they would take it" in r for r in reasons)
    assert any("PR #6 by bob was closed without merging" in r for r in reasons)


def test_pr_check_drops_claims_whose_pr_was_closed_but_keeps_a_new_attempt():
    claim = comment("bob", "I'd like to work on this", "2026-11-23T00:00:00Z")
    closed = xref(6, "bob", "2026-11-23T05:00:00Z", state="closed")
    assert signals(pr_gh(comments=[claim], timeline=[closed]), pr()) == []
    retry = xref(7, "bob", "2026-11-23T09:00:00Z")  # bob opened another one: still on it
    kinds = [s.kind for s in signals(pr_gh(comments=[claim], timeline=[closed, retry]), pr())]
    assert kinds == ["duplicate", "claimed"]


def test_a_failed_burst_search_keeps_the_other_signals(capsys):
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")])
    del gh.data["/search/issues"]  # the fake answers "not found"; GitHub's search limit behaves alike
    assert [s.kind for s in signals(gh, pr(), burst=3)] == ["duplicate"]
    assert "skipped the burst note" in capsys.readouterr().err


def test_many_prs_to_the_same_project_are_not_a_burst():
    gh = pr_gh(search_total=15, repos=0)  # a change split into small PRs, all to this repository
    assert signals(gh, pr(), burst=1) == []


def test_burst_is_off_by_default(monkeypatch):
    monkeypatch.delenv("INPUT_BURST_THRESHOLD", raising=False)
    gh = pr_gh(search_total=50, repos=20)
    gh.data[f"/repos/{REPO}/pulls/20"] = pr()
    monkeypatch.setattr(dibs, "GitHub", lambda token=None: gh)
    assert dibs.main(["pr", "--repo", REPO, "--number", "20", "--dry-run"]) == 0
    assert not any(path == "/search/issues" for path, _ in gh.queries)


def test_comment_is_marked_and_pings_nobody():
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")])
    body = dibs.render_comment(signals(gh, pr()), 20)
    assert body.startswith(dibs.MARKER)
    assert "@" not in body


# ----------------------------------------------------------------------- the Action end to end

def run_action(monkeypatch, tmp_path, gh, the_pr, *args, existing=()):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": the_pr, "repository": {"full_name": REPO}}), encoding="utf-8")
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    gh.data[f"/repos/{REPO}/issues/{the_pr['number']}/comments"] = list(existing)
    monkeypatch.setattr(dibs, "GitHub", lambda token=None: gh)
    code = dibs.main(["pr", *args])
    return code, out.read_text(encoding="utf-8") if out.exists() else ""


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    monkeypatch.setenv("DIBS_NOW", NOW)
    # Tests may run inside GitHub Actions: never read its inputs or write to its output files.
    for name in ("INPUT_FAIL_ON", "INPUT_REQUIRE_DISCLOSURE", "INPUT_COMMENT", "INPUT_LABELS", "INPUT_BURST_THRESHOLD",
                 "GITHUB_EVENT_PATH", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(name, raising=False)


def test_action_posts_one_comment_and_labels(monkeypatch, tmp_path):
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")])
    code, out = run_action(monkeypatch, tmp_path, gh, pr())
    assert code == 0 and "signals=duplicate" in out
    methods = [(m, u.rsplit("/", 2)[-2:]) for m, u, _ in gh.sent]
    assert methods == [("POST", ["20", "comments"]), ("POST", ["20", "labels"])]
    assert gh.sent[1][2] == {"labels": ["dibs: duplicate"]}


def test_action_updates_its_own_comment_instead_of_adding_one(monkeypatch, tmp_path):
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")])
    mine = {"id": 77, "body": dibs.MARKER + "\nold", "user": user("github-actions[bot]", "Bot")}
    run_action(monkeypatch, tmp_path, gh, pr(), "--no-labels", existing=[mine])
    assert [(m, u.rsplit("/", 1)[-1]) for m, u, _ in gh.sent] == [("PATCH", "77")]


def test_action_is_quiet_when_nothing_overlaps(monkeypatch, tmp_path):
    gh = pr_gh()
    code, out = run_action(monkeypatch, tmp_path, gh, pr())
    assert code == 0 and gh.sent == [] and "signals=\n" in out


def test_action_skips_maintainers_and_bots(monkeypatch, tmp_path):
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")])
    run_action(monkeypatch, tmp_path, gh, pr(association="MEMBER"))
    run_action(monkeypatch, tmp_path, gh, pr(login="renovate[bot]"))
    assert gh.sent == []


def test_action_can_fail_the_check(monkeypatch, tmp_path):
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")])
    code, _ = run_action(monkeypatch, tmp_path, gh, pr(), "--fail-on", "duplicate", "--no-comment", "--no-labels")
    assert code == 1


def test_burst_is_never_posted_on_the_pull_request(monkeypatch, tmp_path, capsys):
    gh = pr_gh(search_total=12)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    code, out = run_action(monkeypatch, tmp_path, gh, pr(), "--burst", "3")
    assert code == 0 and "signals=burst" in out  # available to the maintainer's own workflow
    assert gh.sent == []  # no comment, no label
    assert "not posted on the pull request" in summary.read_text(encoding="utf-8")
    assert "not posted on the pull request" in capsys.readouterr().out


def test_burst_stays_off_the_comment_next_to_public_overlap(monkeypatch, tmp_path):
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")], search_total=12)
    code, out = run_action(monkeypatch, tmp_path, gh, pr(), "--burst", "3")
    assert "signals=burst,duplicate" in out
    comment_body, labels = gh.sent[0][2]["body"], gh.sent[1][2]["labels"]
    assert "Earlier pull request" in comment_body and "repositories" not in comment_body
    assert labels == ["dibs: duplicate"]


def test_read_only_token_warns_instead_of_failing(monkeypatch, tmp_path, capsys):
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")])

    def refuse(method, url, body=None):
        raise dibs.GitHubError("GitHub API 403 for POST: Resource not accessible by integration")

    gh.request = refuse
    code, out = run_action(monkeypatch, tmp_path, gh, pr())
    printed = capsys.readouterr().out
    assert code == 0 and "signals=duplicate" in out
    assert "::warning" in printed and "pull_request_target" in printed and "Earlier pull request" in printed


def test_event_without_a_pull_request_is_explained(monkeypatch, tmp_path, capsys):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"issue": {}, "repository": {"full_name": REPO}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert dibs.main(["pr"]) == 3
    assert "pull_request_target" in capsys.readouterr().err


def test_dry_run_posts_nothing(monkeypatch, tmp_path, capsys):
    gh = pr_gh(timeline=[xref(15, "alice", "2026-11-22T00:00:00Z")])
    gh.data[f"/repos/{REPO}/pulls/20"] = pr()
    monkeypatch.setattr(dibs, "GitHub", lambda token=None: gh)
    assert dibs.main(["pr", "--repo", REPO, "--number", "20", "--dry-run"]) == 0
    assert gh.sent == [] and "Earlier pull request" in capsys.readouterr().out
