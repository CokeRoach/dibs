# slugify leaves dashes at the start and end (#42)

Opened by **mira-k**

`slugify` keeps a separator at either end when the text starts or ends with punctuation or dashes:

```python
>>> from slugkit import slugify
>>> slugify("-- Draft --")
'-draft-'
>>> slugify("Notes - ")
'notes-'
```

I expected `'draft'` and `'notes'`. slugkit 1.4.0, Python 3.12.

---

**pmeyer** (maintainer) commented:

> Confirmed, thanks. Happy to take a PR for this; please add a test.
