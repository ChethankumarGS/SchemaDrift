"""Parse SQL DDL or JSON into a small schema model."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


class ParseError(ValueError):
    """Raised when a schema cannot be understood."""


@dataclass
class Column:
    name: str
    type: str
    nullable: bool = True
    default: str | None = None


@dataclass
class Index:
    name: str
    columns: tuple
    unique: bool = False


@dataclass
class Table:
    name: str
    columns: dict = field(default_factory=dict)
    primary_key: tuple = ()
    indexes: dict = field(default_factory=dict)
    foreign_keys: set = field(default_factory=set)  # (column, ref_table, ref_column)


@dataclass
class Schema:
    tables: dict = field(default_factory=dict)


def _clean_ident(s: str) -> str:
    s = s.strip().strip('`"[]')
    if "." in s:  # drop schema prefix such as public.users
        s = s.split(".")[-1].strip('`"[]')
    return s.lower()


def _norm_type(t: str) -> str:
    t = re.sub(r"\s+", " ", t.strip().lower())
    t = re.sub(r"\s*\(\s*", "(", t)
    t = re.sub(r"\s*,\s*", ",", t)
    t = re.sub(r"\s*\)", ")", t)
    aliases = {"integer": "int", "int4": "int", "int8": "bigint", "int2": "smallint",
               "bool": "boolean", "character varying": "varchar", "float8": "double"}
    base = re.match(r"[a-z ]+?(?=\(|$)", t)
    if base and base.group(0).strip() in aliases:
        t = aliases[base.group(0).strip()] + t[len(base.group(0)):]
    return t


def _split_top_level(body: str) -> list:
    parts, depth, cur, quote = [], 0, [], None
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def _cols(s: str) -> tuple:
    return tuple(_clean_ident(c.split()[0]) for c in s.split(",") if c.strip())


_CONSTRAINT_WORDS = ("primary key", "unique", "foreign key", "constraint", "check", "key ", "index ")
_TYPE_STOP = re.compile(
    r"\s+(not\s+null|null|default|primary\s+key|unique|references|check|constraint|"
    r"auto_increment|autoincrement|generated|collate|comment)\b", re.I)


def _parse_column(defn: str, table: Table) -> None:
    m = re.match(r'\s*(`[^`]+`|"[^"]+"|\[[^\]]+\]|\S+)\s+(.*)$', defn, re.S)
    if not m:
        raise ParseError(f"Cannot read column definition: {defn!r}")
    name, rest = _clean_ident(m.group(1)), m.group(2)
    stop = _TYPE_STOP.search(" " + rest)
    type_part = rest if not stop else (" " + rest)[: stop.start()].strip()
    low = rest.lower()
    pk_inline = bool(re.search(r"\bprimary\s+key\b", low))
    nullable = not (re.search(r"\bnot\s+null\b", low) or pk_inline)
    d = re.search(r"\bdefault\s+((?:'[^']*')|(?:\([^)]*\))|(?:[^\s,]+))", rest, re.I)
    default = d.group(1).strip() if d else None
    if re.search(r"\b(serial|bigserial|smallserial)\b", type_part, re.I):
        nullable = False
    table.columns[name] = Column(name, _norm_type(type_part), nullable, default)
    if pk_inline:
        table.primary_key = (name,)
    if re.search(r"\bunique\b", low):
        table.indexes[f"unique_{name}"] = Index(f"unique_{name}", (name,), True)
    r = re.search(r"\breferences\s+(\S+?)\s*\(([^)]*)\)", rest, re.I)
    if r:
        table.foreign_keys.add((name, _clean_ident(r.group(1)), _clean_ident(r.group(2))))


def _parse_table_constraint(defn: str, table: Table) -> bool:
    low = defn.lower().strip()
    low = re.sub(r"^constraint\s+\S+\s+", "", low)
    if not low.startswith(_CONSTRAINT_WORDS):
        return False
    d = re.sub(r"^\s*constraint\s+\S+\s+", "", defn, flags=re.I)
    m = re.match(r"primary\s+key\s*\(([^)]*)\)", d, re.I)
    if m:
        table.primary_key = _cols(m.group(1))
        return True
    m = re.match(r"unique(?:\s+(?:key|index))?\s*(?:\S+\s*)?\(([^)]*)\)", d, re.I)
    if m:
        cols = _cols(m.group(1))
        table.indexes["unique_" + "_".join(cols)] = Index("unique_" + "_".join(cols), cols, True)
        return True
    m = re.match(r"foreign\s+key\s*\(([^)]*)\)\s*references\s+(\S+?)\s*\(([^)]*)\)", d, re.I)
    if m:
        for c, rc in zip(_cols(m.group(1)), _cols(m.group(3))):
            table.foreign_keys.add((c, _clean_ident(m.group(2)), rc))
        return True
    return True  # check constraints and others are ignored


def parse_sql(sql: str) -> Schema:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"(?m)^\s*#[^\n]*", " ", sql)
    schema = Schema()
    stmts = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in stmts:
        m = re.match(
            r"create\s+(?:temp(?:orary)?\s+)?table\s+(?:if\s+not\s+exists\s+)?(\S+?)\s*\((.*)\)[^)]*$",
            stmt, re.I | re.S)
        if m:
            table = Table(_clean_ident(m.group(1)))
            for part in _split_top_level(m.group(2)):
                if not part:
                    continue
                if not _parse_table_constraint(part, table):
                    _parse_column(part, table)
            schema.tables[table.name] = table
            continue
        m = re.match(r"create\s+(unique\s+)?index\s+(?:if\s+not\s+exists\s+)?(\S+)\s+on\s+(\S+?)\s*(?:using\s+\w+\s*)?\((.*)\)", stmt, re.I | re.S)
        if m:
            tname = _clean_ident(m.group(3))
            if tname not in schema.tables:
                raise ParseError(f"Index {m.group(2)} refers to unknown table {tname}")
            name = _clean_ident(m.group(2))
            schema.tables[tname].indexes[name] = Index(name, _cols(m.group(4)), bool(m.group(1)))
            continue
        m = re.match(r"alter\s+table\s+(?:only\s+)?(\S+)\s+add\s+(?:column\s+)?(.*)$", stmt, re.I | re.S)
        if m and _clean_ident(m.group(1)) in schema.tables:
            t = schema.tables[_clean_ident(m.group(1))]
            if not _parse_table_constraint(m.group(2), t):
                _parse_column(m.group(2), t)
    if not schema.tables:
        raise ParseError("No CREATE TABLE statements found.")
    return schema


def parse_json(text: str) -> Schema:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f"Invalid JSON: {e}") from e
    tables = data.get("tables") if isinstance(data, dict) else None
    if not isinstance(tables, dict) or not tables:
        raise ParseError('JSON must look like {"tables": {"users": {"columns": {...}}}}')
    schema = Schema()
    for tname, tdef in tables.items():
        t = Table(tname.lower())
        cols = tdef.get("columns", {})
        for cname, cdef in cols.items():
            if isinstance(cdef, str):
                cdef = {"type": cdef}
            t.columns[cname.lower()] = Column(
                cname.lower(), _norm_type(str(cdef.get("type", "text"))),
                bool(cdef.get("nullable", True)), None if cdef.get("default") is None else str(cdef["default"]))
        t.primary_key = tuple(c.lower() for c in tdef.get("primary_key", []))
        for iname, idef in tdef.get("indexes", {}).items():
            t.indexes[iname.lower()] = Index(iname.lower(), tuple(c.lower() for c in idef.get("columns", [])), bool(idef.get("unique", False)))
        for fk in tdef.get("foreign_keys", []):
            t.foreign_keys.add((fk["column"].lower(), fk["references_table"].lower(), fk["references_column"].lower()))
        schema.tables[t.name] = t
    return schema


def load_schema(text: str) -> Schema:
    """Auto-detect JSON vs SQL DDL."""
    if not text or not text.strip():
        raise ParseError("Schema is empty.")
    if text.lstrip().startswith("{"):
        return parse_json(text)
    return parse_sql(text)
