# Writing the pull request description

If the project has a pull request template, use it: fill in every section, tick only boxes that are true, and keep anything the template asks for. Otherwise use this shape.

    Fixes #123

    What was wrong, in a sentence or two, as the person who reported it saw it.

    Why: the root cause, pointing at the code.

    What this changes, and anything you deliberately left alone.

    Tested: the new test, and the command you ran.

    AI use, in the form the project asks for (or as the user chooses, if it asks for nothing).

## A good one

> Fixes #812
>
> `parse_duration("1h30m")` returned 3600: the pattern was anchored to the start and matched only the first unit, so the minutes were dropped. It now reads every unit in turn and rejects anything left over, so `"1h30x"` still raises.
>
> Tested: a new test for mixed units fails before the change and passes after; `pytest` passes.
>
> AI use: an AI assistant wrote the first version of the fix and the test; I reviewed and simplified both.

It leads with the problem, explains the cause in a way a reviewer can check against the diff, says what was tested, and is no longer than it needs to be.

## One to avoid

> ## 🚀 Summary
> This PR comprehensively addresses issue #812 by implementing a robust and scalable solution for duration parsing.
>
> ## ✨ Changes
> - Updated `duration.py` to improve parsing
> - Added comprehensive tests
> - Improved code quality
>
> ## 🎯 Impact
> Users will now enjoy seamless duration parsing!

It restates the diff, says nothing a reviewer can check, and reads like it was written without looking at the problem. Maintainers have learned to close these on sight.

## Rules of thumb

- Put the issue link and the problem first. The diff already shows which files changed.
- Answer the questions a reviewer would ask: why this approach, what you didn't change, what could break.
- For anything visible, add a screenshot or before-and-after output.
- Keep it as short as the change allows.
