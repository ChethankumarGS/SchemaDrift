import os

from flask import Flask, render_template, request

from schemadrift import ParseError, diff_schemas, load_schema, summarize
from schemadrift.examples import NEW_SQL, OLD_SQL

app = Flask(__name__)


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


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
