"""Run a single chess match between two bot modules.

Each bot exposes `make_move(board) -> chess.Move`. The runner:
  * loads each bot from a file path
  * alternates turns, passing `board.copy()` so bots can't mutate state
  * enforces a 3-second per-move limit (threading.Timer-style, cross-platform)
  * applies a 3-strike system (exception or timeout -> random legal move)
  * enforces a 10-minute per-side clock; on flag-fall, adjudicate by material
  * streams events to the spectator server over Socket.IO
  * writes the completed game to games/<timestamp>.pgn
"""

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import random
import sys
import threading
import time
import traceback
import urllib.request

import chess
import chess.pgn


PER_MOVE_LIMIT = 3.0
PER_SIDE_CLOCK = 600.0  # 10 minutes
MAX_STRIKES = 3

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


# --------------------------------------------------------------------------
# Bot loading
# --------------------------------------------------------------------------

def load_bot(path: str):
    p = pathlib.Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Bot file not found: {p}")
    spec = importlib.util.spec_from_file_location(p.stem, p)
    module = importlib.util.module_from_spec(spec)
    # Give the module a unique name so two bots with the same filename can coexist
    sys.modules[f"_bot_{p.stem}_{id(module)}"] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "make_move"):
        raise AttributeError(f"{p.name} does not define make_move(board)")
    return module, p.stem


# --------------------------------------------------------------------------
# Timed bot call (cross-platform via threading)
# --------------------------------------------------------------------------

class _BotCallResult:
    __slots__ = ("move", "exc")

    def __init__(self):
        self.move = None
        self.exc = None


def call_with_timeout(bot_fn, board_copy, timeout):
    """Call bot_fn(board_copy) with a wall-clock timeout.

    Returns (move, exc, timed_out, elapsed). If timed_out is True, the bot
    thread may still be running in the background as a daemon — we don't try
    to kill it (Python can't, safely). The runner just abandons its result.
    """
    result = _BotCallResult()

    def target():
        try:
            result.move = bot_fn(board_copy)
        except BaseException as e:  # noqa: BLE001 — bots may raise anything
            result.exc = e

    t = threading.Thread(target=target, daemon=True)
    start = time.monotonic()
    t.start()
    t.join(timeout=timeout)
    elapsed = time.monotonic() - start
    if t.is_alive():
        return None, None, True, elapsed
    return result.move, result.exc, False, elapsed


# --------------------------------------------------------------------------
# Material / adjudication helpers
# --------------------------------------------------------------------------

def material_value(board: chess.Board, color: bool) -> int:
    total = 0
    for piece_type, value in PIECE_VALUES.items():
        total += value * len(board.pieces(piece_type, color))
    return total


def captured_pieces(board: chess.Board):
    """Return {white: [symbols of black pieces White captured], black: [...]}.

    Starting pieces minus current pieces of that color = what was captured.
    """
    start_counts = {
        chess.PAWN: 8,
        chess.KNIGHT: 2,
        chess.BISHOP: 2,
        chess.ROOK: 2,
        chess.QUEEN: 1,
        chess.KING: 1,
    }
    out = {"white": [], "black": []}
    # Pieces White captured = missing Black pieces
    for color, key in ((chess.BLACK, "white"), (chess.WHITE, "black")):
        for piece_type, start in start_counts.items():
            present = len(board.pieces(piece_type, color))
            missing = max(0, start - present)
            symbol = chess.Piece(piece_type, color).symbol()
            out[key].extend([symbol] * missing)
    return out


# --------------------------------------------------------------------------
# Visualizer client — plain stdlib HTTP so requirements.txt stays minimal
# (the spec relies on a tiny dependency set to sandbox bots).
# --------------------------------------------------------------------------

class VizClient:
    def __init__(self, enabled: bool, url: str = "http://127.0.0.1:5050"):
        self.enabled = enabled
        self.base_url = url.rstrip("/")
        self.delay = 1.0
        self._failed_once = False
        if not enabled:
            return
        # Probe — if the server isn't up, downgrade to disabled with a warning
        try:
            urllib.request.urlopen(self.base_url + "/delay", timeout=2).read()
        except Exception as e:
            print(f"[warn] Could not reach visualizer at {url}: {e}")
            print("[warn] Continuing without visualization.")
            self.enabled = False

    def emit(self, event, data):
        if not self.enabled:
            return
        payload = json.dumps({"event": event, "data": data}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/event",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=2).read()
        except Exception as e:
            if not self._failed_once:
                print(f"[warn] viz emit failed: {e}")
                self._failed_once = True

    def push_delay(self, delay: float):
        """Tell the server our starting delay (so the slider matches on connect)."""
        self.delay = delay
        if not self.enabled:
            return
        payload = json.dumps({"delay": delay}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/delay",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=2).read()
        except Exception:
            pass

    def refresh_delay(self):
        """Poll the server for the latest delay value (set by the host slider)."""
        if not self.enabled:
            return
        try:
            with urllib.request.urlopen(self.base_url + "/delay", timeout=1) as r:
                body = json.loads(r.read().decode("utf-8"))
            self.delay = float(body.get("delay", self.delay))
        except Exception:
            pass

    def close(self):
        pass


# --------------------------------------------------------------------------
# Main game loop
# --------------------------------------------------------------------------

def run_game(white_path, black_path, delay, no_viz):
    white_bot, white_name = load_bot(white_path)
    black_bot, black_name = load_bot(black_path)

    board = chess.Board()
    viz = VizClient(enabled=not no_viz)
    viz.push_delay(delay)

    clocks = {"white": PER_SIDE_CLOCK, "black": PER_SIDE_CLOCK}
    strikes = {"white": 0, "black": 0}

    viz.emit("game_start", {
        "fen": board.fen(),
        "white_name": white_name,
        "black_name": black_name,
        "clocks": clocks,
    })

    forfeit_side = None  # "white" or "black" if a 3rd strike happens
    flag_fall = False

    while not board.is_game_over(claim_draw=True):
        side_key = "white" if board.turn == chess.WHITE else "black"
        bot = white_bot if board.turn == chess.WHITE else black_bot

        # Cap the per-move limit at remaining clock for this side
        remaining = clocks[side_key]
        if remaining <= 0:
            flag_fall = True
            break
        timeout = min(PER_MOVE_LIMIT, remaining)

        move, exc, timed_out, elapsed = call_with_timeout(
            bot.make_move, board.copy(), timeout
        )

        clocks[side_key] = max(0.0, clocks[side_key] - elapsed)

        struck = False
        strike_reason = None
        if timed_out:
            struck = True
            strike_reason = f"timeout (>{PER_MOVE_LIMIT:.0f}s)"
        elif exc is not None:
            struck = True
            strike_reason = f"exception: {type(exc).__name__}: {exc}"
            print(f"[strike] {side_key} bot raised:")
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        elif move is None:
            struck = True
            strike_reason = "returned None"
        elif move not in board.legal_moves:
            struck = True
            strike_reason = f"illegal move: {move}"

        if struck:
            strikes[side_key] += 1
            print(f"[strike {strikes[side_key]}/{MAX_STRIKES}] {side_key}: {strike_reason}")
            if strikes[side_key] >= MAX_STRIKES:
                forfeit_side = side_key
                # Emit a final status before breaking
                status = f"Forfeit — {side_key} reached {MAX_STRIKES} strikes"
                viz.emit("move", {
                    "fen": board.fen(),
                    "uci": None,
                    "san": None,
                    "strikes": strikes,
                    "clocks": clocks,
                    "captured": captured_pieces(board),
                    "status": status,
                })
                break
            move = random.choice(list(board.legal_moves))

        # Apply the move
        san = board.san(move)
        board.push(move)

        if board.is_checkmate():
            status = f"Checkmate — {('White' if board.turn == chess.BLACK else 'Black')} wins!"
        elif board.is_stalemate():
            status = "Stalemate — draw"
        elif board.is_insufficient_material():
            status = "Draw — insufficient material"
        elif board.can_claim_draw():
            status = "Draw"
        elif board.is_check():
            status = f"Check! {('White' if board.turn == chess.WHITE else 'Black')} to move"
        else:
            status = f"{('White' if board.turn == chess.WHITE else 'Black')} to move"

        viz.emit("move", {
            "fen": board.fen(),
            "uci": move.uci(),
            "san": san,
            "strikes": strikes,
            "clocks": clocks,
            "captured": captured_pieces(board),
            "status": status,
            "struck": struck,
            "strike_side": side_key if struck else None,
            "strike_reason": strike_reason if struck else None,
        })

        print(f"{san:8s}  strikes W:{strikes['white']} B:{strikes['black']}  "
              f"clock W:{clocks['white']:.1f} B:{clocks['black']:.1f}")

        # Visual pacing — pick up any host-slider change since the last move
        viz.refresh_delay()
        time.sleep(max(0.0, viz.delay))

    # ---- Determine result ------------------------------------------------

    result_str = "*"
    end_reason = ""
    if forfeit_side is not None:
        if forfeit_side == "white":
            result_str = "0-1"
            end_reason = "White forfeit (3 strikes)"
        else:
            result_str = "1-0"
            end_reason = "Black forfeit (3 strikes)"
    elif flag_fall:
        white_mat = material_value(board, chess.WHITE)
        black_mat = material_value(board, chess.BLACK)
        if white_mat > black_mat:
            result_str = "1-0"
            end_reason = f"Time-out adjudication: White {white_mat} > Black {black_mat}"
        elif black_mat > white_mat:
            result_str = "0-1"
            end_reason = f"Time-out adjudication: Black {black_mat} > White {white_mat}"
        else:
            result_str = "1/2-1/2"
            end_reason = f"Time-out adjudication: equal material ({white_mat})"
    else:
        outcome = board.outcome(claim_draw=True)
        if outcome is None:
            result_str = "*"
            end_reason = "Game ended"
        else:
            result_str = outcome.result()
            end_reason = outcome.termination.name.replace("_", " ").title()

    print(f"\n=== {result_str} — {end_reason} ===")
    viz.emit("game_end", {
        "result": result_str,
        "reason": end_reason,
        "status": f"{result_str} — {end_reason}",
        "strikes": strikes,
        "clocks": clocks,
    })

    # ---- Save PGN --------------------------------------------------------
    save_pgn(board, white_name, black_name, result_str, end_reason)

    viz.close()


def save_pgn(board, white_name, black_name, result_str, end_reason):
    games_dir = pathlib.Path("games")
    games_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = games_dir / f"{stamp}_{white_name}_vs_{black_name}.pgn"

    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = "Chess Bot Code Jam"
    game.headers["Site"] = "Localhost"
    game.headers["Date"] = dt.datetime.now().strftime("%Y.%m.%d")
    game.headers["White"] = white_name
    game.headers["Black"] = black_name
    game.headers["Result"] = result_str
    game.headers["Termination"] = end_reason

    with open(out_path, "w", encoding="utf-8") as f:
        print(game, file=f)
    print(f"[pgn] saved {out_path}")


def main():
    p = argparse.ArgumentParser(description="Run a single chess bot match.")
    p.add_argument("--white", required=True, help="path to White's bot .py file")
    p.add_argument("--black", required=True, help="path to Black's bot .py file")
    p.add_argument("--delay", type=float, default=1.0,
                   help="seconds to wait between moves (visual pacing)")
    p.add_argument("--no-viz", action="store_true",
                   help="run without the web visualizer")
    args = p.parse_args()
    run_game(args.white, args.black, args.delay, args.no_viz)


if __name__ == "__main__":
    main()
