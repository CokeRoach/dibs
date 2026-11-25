from slugkit import slugify


def test_basic():
    assert slugify("Hello, World!") == "hello-world"


def test_accents():
    assert slugify("Crème brûlée") == "creme-brulee"


def test_separator():
    assert slugify("Hello World", separator="_") == "hello_world"
