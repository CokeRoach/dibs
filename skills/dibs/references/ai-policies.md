# Reading a project's AI policy

Projects word their AI rules in many ways. This is what the common wordings ask of you. When a rule is unclear, the safe reading is the stricter one, and the user can ask the maintainers (in their own words) before starting.

## Where the rules live

- `AI_POLICY.md`, `CONTRIBUTING.md` or `CONTRIBUTING.rst`, at the root, in `.github/` or in `docs/` (dibs looks in all of these)
- the README's "Contributing" section, and the contributing page of the project's documentation site
- the pull request template and issue templates, often as a checkbox ("I used AI tools: yes / no")
- a pinned issue or discussion announcing the policy
- for security reports, `SECURITY.md`

## Common wordings

**"We do not accept AI-generated contributions" / "code written by LLMs".**
The output is banned: no AI-written code, tests, documentation or text in the contribution. Stop and tell the user. Whether you may help them understand the code or the bug is a grey area. Unless the guide says that is fine, treat it as banned as well, and tell the user they are welcome to contribute by hand.

**"No AI-assisted contributions" / "made with the help of AI tools".**
Assistance itself is banned, not just pasted output. Don't help with this contribution at all. You can still help the user with their own code that merely uses the project, such as a workaround in their application, because that is not a contribution.

**"Disclose any use of AI" / "add an `Assisted-by:` trailer" / "tick the AI box".**
Do exactly what it says, in the place it says: a commit trailer, a line in the description, a checkbox. Say what the tool did ("wrote the first version of the fix and the test; I reviewed and changed both"), not just its name.

**"You must understand and be able to explain every line" / "you are responsible for what you submit".**
The user, not you, answers review questions. Walk them through the root cause, the change and the test before they send it (step 5 of the skill), and keep the change small enough that they can.

**"Issues, comments and reviews must be written by people."**
Don't draft text for the project. Give the user the facts (versions, steps to reproduce, links, test results) and let them write it.

**"AI-generated security reports will be closed" / bug bounty rules on AI.**
Never file or draft a vulnerability report from analysis alone. Reproduce it for real, then follow `SECURITY.md`, which usually asks for a private report rather than a public issue.

**Developer Certificate of Origin (`Signed-off-by:`).**
A sign-off is the contributor's statement that they have the right to submit the code under the project's licence. Some projects hold that AI output cannot be certified that way and refuse AI-generated code for that reason, even where they have no separate AI rule. Let the user add the sign-off themselves (`git commit -s`), knowing what it says.

**Contributor licence agreement (CLA).**
A legal agreement the user signs, usually through a bot comment on the PR. Explain what it is; never sign it for them.

## When the project says nothing

Silence is not an invitation to send many PRs. Send one careful PR, mention briefly in the description that AI was used and how, and let the user decide the wording. Maintainers increasingly ask for this, and finding out later costs more trust than saying it up front.
