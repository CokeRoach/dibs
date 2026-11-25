import pytest

from verkit import compare_versions, parse_version


def test_parse_ignores_leading_v():
    assert parse_version("v1.4.2") == parse_version("1.4.2")


@pytest.mark.parametrize("a, b, expected", [
    ("1.4.2", "1.4.2", 0),
    ("1.4.2", "1.5.0", -1),
    ("2.0.0", "1.9.9", 1),
])
def test_compare(a, b, expected):
    assert compare_versions(a, b) == expected


def test_rejects_garbage():
    with pytest.raises(ValueError):
        parse_version("latest")
