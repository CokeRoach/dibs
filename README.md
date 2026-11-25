# dibs

**Is someone already working on this?** A check for both sides of an open-source contribution, read from the issue's own history.

- **For contributors and their coding agents:** an [Agent Skill](#for-contributors-the-agent-skill) that runs before any code is written. It finds open pull requests and "I'll take this" comments on the issue and reads the project's AI policy. Then it works the way the maintainers ask, or not at all if they don't accept AI-made contributions.
- **For maintainers:** a [GitHub Action](#for-maintainers-the-github-action) that tells you, on each new pull request, whether it duplicates an earlier one or takes an issue someone else claimed.

dibs reports facts: who claimed what and when, which pull requests refer to the issue, who it is assigned to, and what the project's guide says. **It never guesses whether a person or a model wrote something.** AI detectors are unreliable, and a wrong guess accuses a real person.

## Why

A popular issue can now draw several pull requests within days, often from people or agents who never read the thread. One open issue we looked at on a busy repository had two open pull requests for the same fix, and two more people saying they would take it. Every extra pull request is review time a maintainer doesn't have, and a contributor's afternoon spent on work that will be closed.

## For maintainers: the GitHub Action

Add `.github/workflows/dibs.yml`:

```yaml
name: dibs
on:
  pull_request_target:
    types: [opened, edited, reopened, synchronize]
permissions:
  issues: write
  pull-requests: write
concurrency:
  group: dibs-${{ github.event.pull_request.number }}
jobs:
  dibs:
    runs-on: ubuntu-latest
    steps:
      - uses: CokeRoach/dibs@v1
```

When a pull request overlaps earlier work, dibs posts one comment, keeps it up to date as things change, and adds a label for each kind of overlap. When nothing overlaps, it stays quiet.

> Thanks for the pull request. Before review, here is some overlap a maintainer will want to know about:
>
> - **Earlier pull request:** #130 by `alice` also refers to #123 and was opened 31 hours earlier: Handle empty config files
> - **Claimed issue:** `bob` said they would take #123 3 days before this PR: "Hi! I'd like to work on this, could you assign it to me?"
>
> If this PR takes a different approach, say how in the description. If it overlaps, consider reviewing or testing the earlier work instead.
>
> <sub>Checked by dibs from the issue and pull request history. It does not judge the code or guess who wrote it.</sub>

| Label | When |
| --- | --- |
| `dibs: duplicate` | An earlier open pull request by someone else refers to the same issue |
| `dibs: claimed` | Someone else said they would take the issue before this pull request was opened, within `claim-days` or with an open pull request of their own |
| `dibs: assigned` | The issue is assigned to someone else |
| `dibs: already-fixed` | A merged pull request already refers to the issue |
| `dibs: burst` | The author opened `burst-threshold` or more pull requests anywhere on GitHub in the 24 hours up to and including this one |
| `dibs: disclosure` | Only if you set `require-disclosure`: the description lacks the AI-use line your guide asks for |

| Input | Default | |
| --- | --- | --- |
| `token` | `github.token` | Reads issues; writes the comment and labels |
| `comment` | `true` | Post and update the comment |
| `labels` | `true` | Add and remove the `dibs:` labels |
| `claim-days` | `21` | How long an "I'd like to work on this" comment counts as a claim |
| `burst-threshold` | `10` | `0` turns the burst check off |
| `require-disclosure` | empty | A regular expression the description must match, such as `^Assisted-by:` |
| `exempt-associations` | `OWNER,MEMBER,COLLABORATOR` | Authors who are never checked |
| `fail-on` | empty | Kinds that fail the check, such as `duplicate,claimed` |

The `signals` output lists the kinds found, comma-separated.

- **Safe on `pull_request_target`.** dibs never checks out or runs the pull request's code. It reads the issue and pull request history through the API, then writes one comment and labels. `pull_request_target` is what lets it comment on pull requests from forks.
- Owners, members, collaborators and bots are never checked, and nobody is @-mentioned.
- The issues come from the pull request's title and description: `Fixes #12`, `#12`, or a link to the issue.
- It uses Python's standard library only, so it runs on any GitHub-hosted runner with no install step.

## For contributors: the Agent Skill

The skill teaches a coding agent (Claude Code, and other agents that read Agent Skills) to contribute the way maintainers want:

1. **Check first.** Before any code, run dibs on the issue. If someone already has a pull request or a recent claim, stop, and offer to review or test their work instead.
2. **Read the house rules.** Read CONTRIBUTING and the AI policy. If the project doesn't accept AI-made contributions, stop and say so. If it asks for disclosure, do exactly what it asks.
3. **Reproduce it on the latest version**, and find where the bug started when that helps.
4. **Make the smallest change**, with a failing test first, and run the project's own checks.
5. **Hand it to the human.** The person sends the pull request, the comments and the sign-off. The agent makes sure they can explain the change.

Install it in Claude Code:

```
/plugin marketplace add CokeRoach/dibs
/plugin install dibs@cokeroach-dibs
```

In other agents, use the [skills CLI](https://github.com/vercel-labs/skills):

```
npx skills add CokeRoach/dibs
```

Or copy `skills/dibs` into your agent's skills folder (`~/.claude/skills/dibs` for Claude Code). Then ask as you normally would, for example "fix https://github.com/OWNER/REPO/issues/123". The skill starts with the check.

## The checker on its own

```
python3 skills/dibs/scripts/dibs.py check https://github.com/OWNER/REPO/issues/123
```

```
dibs: acme/widget#123 "Crash when the config file is empty" (open)
https://github.com/acme/widget/issues/123

STOP  someone is already on this, or it is settled
  - open PR #130 by alice (2026-11-20): Handle empty config files
  - bob said they would take it 3 days ago: "Hi! I'd like to work on this, could you assign it to me?"
  - PR #127 by carol was closed without merging; read why first: https://github.com/acme/widget/pull/127
  · maintainers marked this open for contributors: good first issue (such labels often stay on after someone has taken the issue)

Read before contributing
  - CONTRIBUTING.md  https://github.com/acme/widget/blob/HEAD/CONTRIBUTING.md
      line 112 › Using AI tools:
        AI-assisted contributions are welcome if you disclose them: add an
        `Assisted-by:` trailer to each commit and tick the box in the PR template.
  - pull request template: .github/pull_request_template.md

(4 API requests, no token)
```

The verdict is **GO** (nobody else is on it), **ASK** (an old claim with no pull request, a closed or merged pull request, or a label saying the approach isn't settled) or **STOP**. The exit code is 0, 1 or 2 to match, and 3 on an error. `--json` prints the same facts as JSON.

It uses `GITHUB_TOKEN`, `GH_TOKEN` or a logged-in `gh` when there is one. Without a token GitHub allows 60 requests an hour, and a check takes about four.

Maintainers can check any pull request by hand; `--dry-run` only prints:

```
python3 skills/dibs/scripts/dibs.py pr --repo OWNER/REPO --number 456 --dry-run
```

## Limits

- Claims are recognized in English only: "I'd like to work on this", "can I take this?", "/assign", "I'm on it" and similar. dibs quotes every claim it finds, so you can judge them yourself.
- A pull request is linked to an issue only if it mentions the issue somewhere, which GitHub records on the issue's timeline.
- dibs looks for guides at the usual paths: `CONTRIBUTING` and `AI_POLICY` files at the root, in `.github/` and in `docs/`. A policy that lives only on a documentation site is missed.
- The burst check counts public pull requests, plus any the token can see.

## Development

```
python -m venv .venv
.venv/Scripts/pip install pytest      # .venv/bin/pip on macOS and Linux
.venv/Scripts/python -m pytest
```

The skill's own tests are in `skills/dibs/evals/`, in the layout `claude plugin eval` reads.

## License

MIT
