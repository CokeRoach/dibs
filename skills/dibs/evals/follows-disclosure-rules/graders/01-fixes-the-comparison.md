---
type: llm
focus: trace
weight: 1
---

After the change, compare_versions("1.10.0", "1.9.0") returns 1, compare_versions("1.9.0", "1.10.0") returns -1, and the project's tests pass
