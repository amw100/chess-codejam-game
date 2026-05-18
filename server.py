"""Flask + Socket.IO spectator server for the chess code jam.

Runs as a long-lived process on port 5050. The game_runner connects as a
Socket.IO client and pushes events (`game_start`, `move`, `game_end`); the
server rebroadcasts them to every connected browser. The current game state
is also cached so a browser that joins mid-game gets the latest position.
"""

import pathlib
import subprocess
import sys
import threading

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit


app = Flask(__name__)
app.config["SECRET_KEY"] = "chess-codejam"
# Threading mode — simpler than eventlet, no monkey-patching, fast HTTP
# response times for the runner's POST /event calls. Plenty for a 4-team event.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


BOTS_DIR = pathlib.Path(__file__).parent / "bots"
RUNNER_PATH = pathlib.Path(__file__).parent / "game_runner.py"


STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _default_state():
    return {
        "fen": STARTING_FEN,
        "white_name": "White",
        "black_name": "Black",
        "history_san": [],
        "last_move": None,
        "strikes": {"white": 0, "black": 0},
        "clocks": {"white": 120.0, "black": 120.0},
        "captured": {"white": [], "black": []},
        "status": "Waiting for game…",
        "delay": 1.0,
        "game_over": False,
        "running": False,
        "turn": "white",
    }


state = _default_state()

# Subprocess handle for the currently running game (None if idle).
_proc_lock = threading.Lock()
_proc = None  # type: subprocess.Popen | None


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("connect")
def on_connect():
    emit("state", state)


# ---- Events from the game_runner (HTTP POST, stdlib-friendly) -----------
#
# The runner posts {"event": "...", "data": {...}} to /event. We mutate
# the cached state and rebroadcast over Socket.IO to all browsers. Using
# plain HTTP here means the runner needs nothing beyond stdlib — keeping
# requirements.txt minimal so bots can't import anything extra.

def _handle_game_start(data):
    state.update({
        "fen": data.get("fen", state["fen"]),
        "white_name": data.get("white_name", "White"),
        "black_name": data.get("black_name", "Black"),
        "history_san": [],
        "last_move": None,
        "strikes": {"white": 0, "black": 0},
        "clocks": data.get("clocks", {"white": 120.0, "black": 120.0}),
        "captured": {"white": [], "black": []},
        "status": "White to move",
        "game_over": False,
        "turn": data.get("turn", "white"),
    })
    socketio.emit("game_start", state)


def _handle_move(data):
    state["fen"] = data.get("fen", state["fen"])
    state["last_move"] = data.get("uci")
    san = data.get("san")
    if san:
        state["history_san"].append(san)
    if "strikes" in data:
        state["strikes"] = data["strikes"]
    if "clocks" in data:
        state["clocks"] = data["clocks"]
    if "captured" in data:
        state["captured"] = data["captured"]
    if "status" in data:
        state["status"] = data["status"]
    if "turn" in data:
        state["turn"] = data["turn"]
    socketio.emit("move", data)


def _handle_game_end(data):
    state["status"] = data.get("status", "Game over")
    state["game_over"] = True
    socketio.emit("game_end", data)


_EVENT_HANDLERS = {
    "game_start": _handle_game_start,
    "move": _handle_move,
    "game_end": _handle_game_end,
}


@app.route("/event", methods=["POST"])
def post_event():
    body = request.get_json(silent=True) or {}
    event = body.get("event")
    data = body.get("data", {})
    handler = _EVENT_HANDLERS.get(event)
    if handler is None:
        return jsonify({"ok": False, "error": f"unknown event {event!r}"}), 400
    handler(data)
    return jsonify({"ok": True})


@app.route("/delay", methods=["GET", "POST"])
def delay_route():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        try:
            d = float(body.get("delay", state["delay"]))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "bad delay"}), 400
        state["delay"] = d
        socketio.emit("delay_changed", {"delay": d})
    return jsonify({"delay": state["delay"]})


# ---- Control endpoints (browser → server) -------------------------------

@app.route("/bots", methods=["GET"])
def list_bots():
    if not BOTS_DIR.exists():
        return jsonify({"bots": []})
    bots = sorted(
        p.name for p in BOTS_DIR.glob("*.py") if not p.name.startswith("_")
    )
    return jsonify({"bots": bots})


def _broadcast_control_state():
    socketio.emit("control_state", {"running": state["running"]})


def _watch_process(proc):
    """Wait for the runner to exit, then mark idle and notify clients."""
    proc.wait()
    with _proc_lock:
        global _proc
        if _proc is proc:
            _proc = None
        state["running"] = False
    _broadcast_control_state()


@app.route("/control/start", methods=["POST"])
def control_start():
    global _proc
    body = request.get_json(silent=True) or {}
    white = body.get("white")
    black = body.get("black")
    if not white or not black:
        return jsonify({"ok": False, "error": "white and black required"}), 400

    # Resolve and validate bot paths — must live under bots/.
    def resolve(name):
        p = (BOTS_DIR / name).resolve()
        try:
            p.relative_to(BOTS_DIR.resolve())
        except ValueError:
            return None
        return p if p.exists() else None

    white_path = resolve(white)
    black_path = resolve(black)
    if not white_path or not black_path:
        return jsonify({"ok": False, "error": "bot not found"}), 400

    with _proc_lock:
        if _proc is not None and _proc.poll() is None:
            return jsonify({"ok": False, "error": "game already running"}), 409
        cmd = [
            sys.executable, str(RUNNER_PATH),
            "--white", str(white_path),
            "--black", str(black_path),
            "--delay", str(state["delay"]),
        ]
        _proc = subprocess.Popen(cmd, cwd=str(pathlib.Path(__file__).parent))
        state["running"] = True

    threading.Thread(target=_watch_process, args=(_proc,), daemon=True).start()
    _broadcast_control_state()
    return jsonify({"ok": True})


@app.route("/control/stop", methods=["POST"])
def control_stop():
    global _proc
    with _proc_lock:
        if _proc is None or _proc.poll() is not None:
            state["running"] = False
            _broadcast_control_state()
            return jsonify({"ok": True, "note": "not running"})
        _proc.terminate()
    # The watcher thread will flip running=False once the process exits.
    return jsonify({"ok": True})


@app.route("/control/reset", methods=["POST"])
def control_reset():
    with _proc_lock:
        if _proc is not None and _proc.poll() is None:
            return jsonify({"ok": False, "error": "stop the game first"}), 409
    delay = state["delay"]
    state.clear()
    state.update(_default_state())
    state["delay"] = delay
    socketio.emit("state", state)
    return jsonify({"ok": True})


# ---- Events from the browser --------------------------------------------

@socketio.on("set_delay")
def on_set_delay(data):
    try:
        d = float(data.get("delay", state["delay"]))
    except (TypeError, ValueError):
        return
    state["delay"] = d
    socketio.emit("delay_changed", {"delay": d})


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5050)
