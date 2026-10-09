import pytest

from schemadrift import ParseError, load_schema


def test_parses_columns_defaults_and_pk():
    s = load_schema("""
      CREATE TABLE IF NOT EXISTS public."Users" (
        id SERIAL PRIMARY KEY,
        email VARCHAR(100) NOT NULL DEFAULT 'a,b',
        score NUMERIC(10, 2),
        UNIQUE (email),
        CONSTRAINT fk FOREIGN KEY (id) REFERENCES other(id)
      );""")
    t = s.tables["users"]
    assert t.primary_key == ("id",)
    assert t.columns["email"].nullable is False
    assert t.columns["email"].default == "'a,b'"
    assert t.columns["score"].type == "numeric(10,2)"
    assert ("id", "other", "id") in t.foreign_keys
    assert any(i.unique for i in t.indexes.values())


def test_comments_are_ignored():
    s = load_schema("-- hi\nCREATE TABLE a (x INT); /* c */")
    assert "x" in s.tables["a"].columns


def test_type_aliases_normalised():
    s = load_schema("CREATE TABLE a (x INTEGER, y CHARACTER VARYING(10), z BOOL);")
    cols = s.tables["a"].columns
    assert (cols["x"].type, cols["y"].type, cols["z"].type) == ("int", "varchar(10)", "boolean")


@pytest.mark.parametrize("bad", ["", "   ", "SELECT 1;", "{not json", '{"tables": {}}'])
def test_bad_input_raises(bad):
    with pytest.raises(ParseError):
        load_schema(bad)
