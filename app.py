import json
import os
from dataclasses import asdict

from flask import Flask, jsonify, render_template, request

from schemadrift import ParseError, diff_schemas, load_schema, summarize
from schemadrift.examples import NEW_SQL, OLD_SQL

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024  # schemas are text; reject huge uploads


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        old_text = request.form.get("old_schema", "")
        new_text = request.form.get("new_schema", "")
    else:
        old_text, new_text = OLD_SQL, NEW_SQL
    changes, summary, error = [], None, None
    try:
        changes = diff_schemas(load_schema(old_text), load_schema(new_text))
        summary = summarize(changes)
    except ParseError as e:
        error = str(e)
    return render_template("index.html", old_text=old_text, new_text=new_text,
                           changes=changes, summary=summary, error=error)


def _as_text(value):
    """Accept schema text, or a JSON object that we serialise."""
    if isinstance(value, dict):
        return json.dumps(value)
    return value if isinstance(value, str) else None


@app.post("/api/diff")
def api_diff():
    """JSON API for CI: POST {"old": ..., "new": ...}, get the changes and a verdict."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON body with 'old' and 'new'."), 400
    old, new = _as_text(data.get("old")), _as_text(data.get("new"))
    if old is None or new is None:
        return jsonify(error="'old' and 'new' must be SQL text or a JSON schema object."), 400
    try:
        changes = diff_schemas(load_schema(old), load_schema(new))
    except ParseError as e:
        return jsonify(error=str(e)), 422
    return jsonify(summary=summarize(changes), changes=[asdict(c) for c in changes])


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="Schema too large (limit 512 KB)."), 413


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
