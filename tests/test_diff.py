from schemadrift import diff_schemas, load_schema, summarize
from schemadrift.examples import NEW_SQL, OLD_SQL


def run(old, new):
    return diff_schemas(load_schema(old), load_schema(new))


def kinds(changes, severity=None):
    return {(c.kind, c.column) for c in changes if severity in (None, c.severity)}


BASE = "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(50), n INT);"


def test_identical_schemas_have_no_changes():
    assert run(BASE, BASE) == []
    assert summarize([])["verdict"] == "NO CHANGES"


def test_table_added_is_safe_and_dropped_is_breaking():
    two = BASE + " CREATE TABLE u (id INT PRIMARY KEY);"
    assert kinds(run(BASE, two), "safe") == {("table_added", None)}
    assert kinds(run(two, BASE), "breaking") == {("table_removed", None)}


def test_column_dropped_is_breaking():
    new = "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(50));"
    assert ("column_removed", "n") in kinds(run(BASE, new), "breaking")


def test_nullable_column_added_is_safe():
    new = BASE.replace("n INT", "n INT, extra TEXT")
    assert ("column_added", "extra") in kinds(run(BASE, new), "safe")


def test_not_null_column_without_default_is_breaking():
    new = BASE.replace("n INT", "n INT, extra TEXT NOT NULL")
    assert ("column_added_required", "extra") in kinds(run(BASE, new), "breaking")


def test_not_null_column_with_default_is_safe():
    new = BASE.replace("n INT", "n INT, extra INT NOT NULL DEFAULT 0")
    assert ("column_added", "extra") in kinds(run(BASE, new), "safe")


def test_int_widening_safe_narrowing_breaking():
    wide = BASE.replace("n INT", "n BIGINT")
    assert ("type_changed", "n") in kinds(run(BASE, wide), "safe")
    assert ("type_changed", "n") in kinds(run(wide, BASE), "breaking")


def test_varchar_growth_safe_shrink_breaking():
    big = BASE.replace("VARCHAR(50)", "VARCHAR(200)")
    assert ("type_changed", "name") in kinds(run(BASE, big), "safe")
    assert ("type_changed", "name") in kinds(run(big, BASE), "breaking")


def test_incompatible_type_change_is_breaking():
    new = BASE.replace("n INT", "n TEXT")
    assert ("type_changed", "n") in kinds(run(BASE, new), "breaking")


def test_nullability_tightened_is_breaking():
    old = "CREATE TABLE t (id INT PRIMARY KEY, n INT);"
    new = "CREATE TABLE t (id INT PRIMARY KEY, n INT NOT NULL);"
    assert ("nullability_tightened", "n") in kinds(run(old, new), "breaking")
    assert ("nullability_relaxed", "n") in kinds(run(new, old), "safe")


def test_primary_key_change_is_breaking():
    new = "CREATE TABLE t (id INT, name VARCHAR(50), n INT, PRIMARY KEY (id, n));"
    assert ("primary_key_changed", None) in kinds(run(BASE, new), "breaking")


def test_unique_index_added_is_breaking_plain_index_is_safe():
    uq = BASE + " CREATE UNIQUE INDEX u ON t (name);"
    ix = BASE + " CREATE INDEX i ON t (name);"
    assert ("unique_added", None) in kinds(run(BASE, uq), "breaking")
    assert ("index_added", None) in kinds(run(BASE, ix), "safe")
    assert ("index_removed", None) in kinds(run(ix, BASE), "warning")


def test_rename_is_reported_as_drop_plus_add_with_hint():
    new = BASE.replace("name VARCHAR(50)", "full_name VARCHAR(50)")
    changes = run(BASE, new)
    dropped = [c for c in changes if c.kind == "column_removed"][0]
    assert "rename" in dropped.message.lower()


def test_json_input_matches_sql_input():
    js = '{"tables": {"t": {"columns": {"id": {"type": "int", "nullable": false}}, "primary_key": ["id"]}}}'
    new = '{"tables": {"t": {"columns": {"id": {"type": "bigint", "nullable": false}, "x": "text"}, "primary_key": ["id"]}}}'
    ks = kinds(run(js, new))
    assert ("type_changed", "id") in ks and ("column_added", "x") in ks


def test_builtin_example_has_all_three_levels():
    s = summarize(run(OLD_SQL, NEW_SQL))
    assert s["breaking"] >= 5 and s["warning"] >= 1 and s["safe"] >= 3
    assert s["verdict"] == "BREAKING"
