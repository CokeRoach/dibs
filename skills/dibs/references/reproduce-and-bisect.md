# Reproduce, then find where it started

## Reproduce on the latest version

Use a fresh environment so nothing on the machine hides or causes the bug.

- Python: `python -m venv repro-env`, then `repro-env/bin/pip install -U PACKAGE` (on Windows, `repro-env\Scripts\pip`).
- JavaScript: `npm install PACKAGE@latest` in an empty folder.
- From source: `git clone --filter=blob:none URL`, then build the default branch the way CONTRIBUTING says.

Write the smallest program that shows the bug: the imports, the few lines that trigger it, and what it prints. Note the versions (package, language, operating system). A reproduction short enough to paste into a comment is the most useful thing you can give a maintainer.

If it no longer happens on the latest version, say so on the issue (with the version you tried and your steps) instead of sending a pull request.

## Find the first bad release

List the releases:

- PyPI: `pip index versions PACKAGE`, or `https://pypi.org/pypi/PACKAGE/json`
- npm: `npm view PACKAGE versions --json`
- GitHub: `gh release list -R OWNER/REPO`

Then search by halves: install the release midway between one known to be good and one known to be bad, run the reproduction, and keep the half that still contains the change. Use a fresh environment for every install. Twenty releases take about five tries.

## Find the first bad commit

    git bisect start
    git bisect bad                 # the current commit has the bug
    git bisect good v4.3.0         # a tag or commit that does not
    git bisect run ./repro.sh      # exit 0 = good, 1 to 124 = bad, 125 = cannot test this commit
    git bisect reset

`repro.sh` builds the project if it needs to and runs the reproduction. Make it exit with 125 when the build itself fails, so that bisect skips that commit instead of blaming it.

## Report what you found

A comment like this is often enough for a maintainer to fix the bug in minutes, and it helps even if no patch follows:

> Still happens on 4.6.1 (Python 3.12, Ubuntu 24.04). It started in 4.4.0; 4.3.2 is fine.
>
> ```python
> from pkg import parse
> print(parse("1h30m"))   # 3600.0, expected 5400.0
> ```
>
> First bad commit: abc1234 "Simplify the unit parser", which anchored the pattern to the first unit.
