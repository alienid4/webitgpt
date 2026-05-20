from __future__ import annotations

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "component": "webitgpt-edge", "port": 9444})


@app.post("/cmd")
def cmd():
    payload = request.get_json(force=True, silent=True) or {}
    return jsonify({"status": "accepted", "cmd": payload.get("cmd"), "stub": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9444)

