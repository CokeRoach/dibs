# compare_versions says 1.10.0 is older than 1.9.0 (#17)

Opened by **tomasz-w**

```python
>>> from verkit import compare_versions
>>> compare_versions("1.10.0", "1.9.0")
-1
```

1.10.0 is the newer version, so I expected `1`. verkit 2.1.0, Python 3.12.

---

**lena-ortiz** (maintainer) commented:

> Good catch: the parts are compared as text, so "10" sorts before "9". A PR is welcome; please include a test.
