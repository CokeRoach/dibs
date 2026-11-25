---
name: dibs
description: Before working on an issue or pull request in someone else's open-source project, check whether anyone is already on it and what the project's rules say about AI, then contribute the way its maintainers ask. Use this skill whenever the user wants to fix a GitHub issue, send a pull request, "contribute to" or "help out with" a repository they don't maintain, find a good first issue, or draft a PR description, issue comment or reply to a maintainer, even if they only paste an issue link and say "fix this". Run it before writing any code. Also use it when a maintainer wants to know whether an incoming pull request duplicates earlier work.
---

# dibs

Open-source maintainers now spend much of their week closing pull requests that should never have been opened: a second fix for an issue that already has an open PR, a fix for an issue someone else said they were taking, a change that ignores the project's rules on AI, a patch nobody ran. Each one costs a maintainer more time to close than it cost to make.

This skill is the opposite habit. Before any code, find out whether someone is already on it and what the project asks of contributors. Then make one small, tested change and hand it to the person whose name goes on it.

## 1. Call dibs first

Run the checker that comes with this skill (in `scripts/` next to this file; use `python` where `python3` is not found):

    python3 <this skill's folder>/scripts/dibs.py check https://github.com/OWNER/REPO/issues/123

It reads the issue, its comments and timeline, and the project's contributing guide and AI policy, then prints one of three verdicts with its reasons:

- **STOP**: someone has an open or draft PR for it, it is assigned to someone else, someone said they would take it in the last three weeks, or it is closed or labelled won't-fix.
- **ASK**: someone claimed it a while ago and has not opened a PR, a PR about it was merged or closed, or a label says the approach is still being decided.
- **GO**: nobody else is on it.

It also lists the guide files it found and quotes every passage in them that mentions AI. The exit code is 0 for GO, 1 for ASK, 2 for STOP and 3 for an error; `--json` gives the same facts as JSON. If you know the user's GitHub login and no token is set, pass `--me LOGIN` so their own claims and PRs don't count against them.

dibs finds claims by their wording ("I'd like to work on this", "/assign"), so read each quoted comment yourself: it can miss a claim, or quote one that isn't.

Without a token GitHub allows 60 requests an hour, and a check takes about four. If dibs says the rate limit is reached, tell the user when it resets and that `gh auth login` or a `GITHUB_TOKEN` lifts the limit; don't retry in a loop. If there is no GitHub issue (the user found the bug themselves, or the repository is private or offline), skip the check but still do step 2.

Then act on the verdict.

**STOP.** Don't write a competing fix, even a better one. A second PR splits the reviewers' attention, and one of the two usually ends up closed. Tell the user who is already on it, with links, and offer what actually helps:

- review or test the open PR: check it out, run its tests, try it against the original report, and draft a comment with what you found for the user to post;
- if the open PR looks abandoned (no activity for months), draft a short, polite question to its author asking whether they are still on it; only their reply, or a maintainer, frees the issue;
- or find another issue (see "Finding an issue" below).

**ASK.** Draft a one- or two-sentence question for the user to post: to the claimant ("Are you still working on this? If not, I'd like to try.") or to the maintainers ("Is this still wanted, and would approach X be acceptable?"). While waiting you may reproduce the bug locally (step 3), which makes the question more useful. Don't start the fix until someone answers.

**GO.** Still read the guide (step 2). Many projects want a comment before work starts; if the guide says so, draft one for the user.

## 2. Read the house rules

Open the files dibs listed and read them in full, not only the quoted AI passages: CONTRIBUTING, any AI policy, the pull request template, and the README's contributing section. If dibs found none, look in the README and the project's documentation site.

- **AI rules.** If the project does not accept AI-generated or AI-assisted contributions, stop here and tell the user, quoting the rule and linking to it. Don't look for a way around it ("it's a one-line fix", "you could retype it"): the maintainers have decided, and the user can still contribute by hand. If the project asks for disclosure, note exactly the form it wants (a trailer such as `Assisted-by:`, a checkbox, a sentence in the description) so you include it later. Some projects also ask that issues and comments be written by people; there, wherever this skill says "draft", give the user the facts (versions, steps, links) and let them write the words. `references/ai-policies.md` covers the common wordings and what each asks of you.
- **Process.** Whether to comment or get approval before starting; the branch to target and how to name yours; commit message style; changelog entries; the tests and checks that must pass; sign-off (DCO) and contributor agreements (CLA). A sign-off and a CLA are the user's own legal statements, so explain them and let the user make them.

## 3. Reproduce it on the latest version

Before changing anything, make the bug happen on the latest release or the default branch. Many bugs in older issues are already fixed or behave differently now. If it doesn't reproduce, the contribution is a comment saying so, with the version and steps, not a pull request.

If it does reproduce, finding where it started is often worth more to a maintainer than a patch: try releases in between, or `git bisect run`, until you have the first bad version or commit. `references/reproduce-and-bisect.md` has the commands.

Keep clones small. `git clone --filter=blob:none` keeps the history you need for bisecting without downloading every old file.

## 4. Make the smallest change that fixes it

- Start with a test that fails for the reported case, in the project's own test style and folder. Then fix it, and watch the test pass.
- Change only what the fix needs. No reformatting, renaming, drive-by refactors or new dependencies: every extra line is something a maintainer has to read, and a reason to turn the whole PR down.
- Match the surrounding code, even where you would write it differently.
- Run the project's own checks (tests, linters, type checks, pre-commit hooks) the way CONTRIBUTING or the CI configuration runs them. Never skip hooks with `--no-verify`, never weaken or delete a test to get a pass, and if a check fails for a reason unrelated to your change, say so rather than "fixing" it.
- If the real fix turns out bigger than the issue suggests (an API change, a design choice), stop and draft a question for the maintainers instead of sending a large PR nobody agreed to.

## 5. Hand it to the human

The user is the contributor and you are their tool. Everything the project sees goes out under their name, so they send it: don't push, fork, open the PR, comment or request reviewers unless the user tells you to do that specific thing. Make each of those a single step for them instead.

- **Make sure they can explain it.** Summarize the root cause and the fix in plain words, and point to the test that proves it. A maintainer will ask questions, and the user should be able to answer without coming back to you.
- **Commit** in the project's style, on a branch named the way the guide asks. Use the attribution the project asks for in step 2. If it asks for nothing, ask the user how they want AI use noted rather than deciding for them; a line in the PR description is the usual minimum. Use the user's GitHub noreply address if they would rather not publish their email.
- **Write the PR description** from the project's template if it has one (dibs names it), filling in every section and ticking only boxes that are true. Otherwise use the short shape in `references/pr-description.md`. Say what was wrong, why, what changed and how it was tested, and link the issue with `Fixes #N` so GitHub connects them. Write it at the size of the change: a two-line fix gets a few sentences, not headings, emoji and a summary of the diff.
- **One PR per issue.** If you noticed other problems along the way, list them for the user to report separately.

## 6. After the PR is open

- Review comments are addressed to the user. Help them understand each one and make the requested changes as new commits, unless the project asks for a rebase or squash.
- If CI fails, read the log and fix the actual cause.
- Don't nudge maintainers sooner than the guide suggests (often a week or two); then draft one short, polite reminder.
- If they decline or close it, that is their call. Help the user ask what would make it acceptable, or move on.

## Finding an issue

If the user wants to contribute but has no issue in mind, look for issues labelled `good first issue` or `help wanted` in projects they actually use, and run `dibs.py check` on each candidate before suggesting it. Suggest only GO issues, and say why each one suits the user. Issues on very popular repositories are often claimed within hours; smaller projects they already use are usually a better start.

## What maintainers recognize as low-effort AI contributions

Check your work against this list before handing it over:

- a PR for an issue that already has an open PR or a recent claim;
- code or tests that were never run, or tests that assert nothing;
- changes unrelated to the issue, or a whole file reformatted;
- functions, options or packages that don't exist in the project;
- a description longer than the diff, bullet lists restating the diff, filler ("comprehensive", "robust", "seamless"), emoji headings;
- replies to review comments that are pasted model output instead of the user's own understanding;
- many PRs to many projects at once, or typo-only PRs sent to fill a contribution graph.

## For maintainers

The same script checks an incoming pull request for overlap: an earlier open PR for the same issue, a claim by someone else, an assignee, or an issue that is already fixed.

    python3 <this skill's folder>/scripts/dibs.py pr --repo OWNER/REPO --number 456 --dry-run

`--dry-run` only prints. To run the check on every new pull request, the repository this skill comes from is also a GitHub Action; its README shows the workflow: https://github.com/CokeRoach/dibs
