"""Compare two schemas and classify every change."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .parser import Schema

BREAKING, WARNING, SAFE = "breaking", "warning", "safe"

_INT_RANK = {"smallint": 1, "int": 2, "bigint": 3}
_FLOAT_RANK = {"real": 1, "float": 1, "double": 2}


@dataclass
class Change:
    table: str
    kind: str          # e.g. column_removed
    severity: str      # breaking | warning | safe
    message: str
    column: str | None = None
    old: str | None = None
    new: str | None = None


def _base_args(t: str):
    m = re.match(r"([a-z ]+?)\s*(?:\(([^)]*)\))?$", t)
    if not m:
        return t, ()
    args = tuple(int(a) for a in m.group(2).split(",") if a.strip().isdigit()) if m.group(2) else ()
    return m.group(1).strip(), args


def type_change_severity(old: str, new: str) -> tuple:
    """Return (severity, reason) for changing a column type."""
    ob, oa = _base_args(old)
    nb, na = _base_args(new)
    if ob in _INT_RANK and nb in _INT_RANK:
        return (SAFE, "integer widened") if _INT_RANK[nb] >= _INT_RANK[ob] else (BREAKING, "integer narrowed, values may overflow")
    if ob in _FLOAT_RANK and nb in _FLOAT_RANK:
        return (SAFE, "float widened") if _FLOAT_RANK[nb] >= _FLOAT_RANK[ob] else (BREAKING, "float precision reduced")
    if ob in ("varchar", "char") and nb in ("varchar", "char", "text"):
        if nb == "text":
            return SAFE, "now unbounded text"
        if oa and na:
            return (SAFE, "length increased") if na[0] >= oa[0] else (BREAKING, "length reduced, values may be truncated")
        return WARNING, "length changed"
    if ob == "text" and nb in ("varchar", "char"):
        return BREAKING, "text narrowed to a bounded type"
    if ob == "decimal" or ob == "numeric":
        if nb in ("decimal", "numeric") and len(oa) == 2 and len(na) == 2:
            if na[0] >= oa[0] and na[1] >= oa[1] and (na[0] - na[1]) >= (oa[0] - oa[1]):
                return SAFE, "precision increased"
            return BREAKING, "precision or scale reduced"
    return BREAKING, "incompatible type change"


def diff_schemas(old: Schema, new: Schema) -> list:
    changes: list = []
    for t in sorted(set(old.tables) - set(new.tables)):
        changes.append(Change(t, "table_removed", BREAKING, f"Table {t} was dropped. Code reading or writing it will fail."))
    for t in sorted(set(new.tables) - set(old.tables)):
        changes.append(Change(t, "table_added", SAFE, f"New table {t} added."))
    for tname in sorted(set(old.tables) & set(new.tables)):
        o, n = old.tables[tname], new.tables[tname]
        removed = [c for c in o.columns if c not in n.columns]
        added = [c for c in n.columns if c not in o.columns]
        for c in removed:
            hint = ""
            same = [a for a in added if n.columns[a].type == o.columns[c].type]
            if same:
                hint = f" Possible rename to {same[0]}; a rename is still breaking for old code."
            changes.append(Change(tname, "column_removed", BREAKING, f"Column {tname}.{c} was dropped.{hint}", c, o.columns[c].type))
        for c in added:
            col = n.columns[c]
            if not col.nullable and col.default is None:
                changes.append(Change(tname, "column_added_required", BREAKING,
                                      f"Column {tname}.{c} is NOT NULL with no default. Existing rows and old INSERTs will fail.", c, None, col.type))
            else:
                changes.append(Change(tname, "column_added", SAFE, f"Column {tname}.{c} ({col.type}) added.", c, None, col.type))
        for c in sorted(set(o.columns) & set(n.columns)):
            oc, nc = o.columns[c], n.columns[c]
            if oc.type != nc.type:
                sev, why = type_change_severity(oc.type, nc.type)
                changes.append(Change(tname, "type_changed", sev, f"{tname}.{c} type {oc.type} -> {nc.type} ({why}).", c, oc.type, nc.type))
            if oc.nullable and not nc.nullable:
                sev = SAFE if nc.default is not None else BREAKING
                changes.append(Change(tname, "nullability_tightened", BREAKING if sev == BREAKING else WARNING,
                                      f"{tname}.{c} is now NOT NULL. " + ("Existing NULLs and old writes will fail." if sev == BREAKING else "A default exists, but existing NULL rows still need a backfill."),
                                      c, "NULL", "NOT NULL"))
            elif not oc.nullable and nc.nullable:
                changes.append(Change(tname, "nullability_relaxed", SAFE, f"{tname}.{c} now allows NULL. Readers that assume non-null may break.", c, "NOT NULL", "NULL"))
            if oc.default != nc.default and oc.type == nc.type:
                if nc.default is None:
                    changes.append(Change(tname, "default_removed", WARNING, f"{tname}.{c} lost its default ({oc.default}). Inserts that omit it may fail.", c, oc.default, None))
                else:
                    changes.append(Change(tname, "default_changed", SAFE if oc.default is None else WARNING,
                                          f"{tname}.{c} default {oc.default} -> {nc.default}.", c, oc.default, nc.default))
        if o.primary_key != n.primary_key:
            changes.append(Change(tname, "primary_key_changed", BREAKING,
                                  f"Primary key of {tname} changed from ({', '.join(o.primary_key) or 'none'}) to ({', '.join(n.primary_key) or 'none'}).",
                                  None, ",".join(o.primary_key), ",".join(n.primary_key)))
        for i in sorted(set(o.indexes) - set(n.indexes)):
            ix = o.indexes[i]
            sev = BREAKING if ix.unique else WARNING
            msg = f"{'Unique constraint' if ix.unique else 'Index'} {i} on {tname}({', '.join(ix.columns)}) removed." + (" Duplicates are now allowed." if ix.unique else " Queries may slow down.")
            changes.append(Change(tname, "index_removed", sev, msg))
        for i in sorted(set(n.indexes) - set(o.indexes)):
            ix = n.indexes[i]
            if ix.unique:
                changes.append(Change(tname, "unique_added", BREAKING, f"Unique constraint {i} on {tname}({', '.join(ix.columns)}) added. Existing duplicate rows will block the migration."))
            else:
                changes.append(Change(tname, "index_added", SAFE, f"Index {i} on {tname}({', '.join(ix.columns)}) added."))
        for fk in sorted(o.foreign_keys - n.foreign_keys):
            changes.append(Change(tname, "fk_removed", WARNING, f"Foreign key {tname}.{fk[0]} -> {fk[1]}.{fk[2]} removed. Integrity is no longer enforced."))
        for fk in sorted(n.foreign_keys - o.foreign_keys):
            changes.append(Change(tname, "fk_added", WARNING, f"Foreign key {tname}.{fk[0]} -> {fk[1]}.{fk[2]} added. Orphan rows will block the migration."))
    order = {BREAKING: 0, WARNING: 1, SAFE: 2}
    changes.sort(key=lambda c: (order[c.severity], c.table, c.kind, c.column or ""))
    return changes


def summarize(changes: list) -> dict:
    counts = {BREAKING: 0, WARNING: 0, SAFE: 0}
    for c in changes:
        counts[c.severity] += 1
    counts["total"] = len(changes)
    counts["verdict"] = "BREAKING" if counts[BREAKING] else ("REVIEW" if counts[WARNING] else ("SAFE" if changes else "NO CHANGES"))
    return counts
