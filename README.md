# Chess Bot Code Jam

A 2-hour, 4-team chess bot tournament. You write one function; the rest of the system runs the game and shows it on a big screen.

## Setup

```bash
pip install -r requirements.txt
```

## Run

In one terminal, start the spectator server:

```bash
python server.py
```

Open <http://localhost:5050> in a browser.

In another terminal, run a match:

```bash
python game_runner.py --white bots/random_bot.py --black bots/greedy_bot.py --delay 1.0
```

Headless (no visualizer, for quick testing):

```bash
python game_runner.py --white bots/my_bot.py --black bots/random_bot.py --no-viz
```

Completed games are saved as PGN under `games/`.

## Your job

Edit `bots/my_bot.py`. Implement:

```python
def make_move(board: chess.Board) -> chess.Move:
    ...
```

That's it. Return a legal `chess.Move`. No game loop, no UI, no networking.

## Rules

- **Per-move limit:** 3 seconds. Exceed it → random legal move is played for you and you take a strike.
- **Per-game clock:** 10 minutes per side. Flag fall → adjudicated by material (P=1, N=3, B=3, R=5, Q=9).
- **Strikes:** Raise an exception (or return `None`) → strike. Time out → strike. 3 strikes → forfeit.
- **Allowed imports:** Python stdlib and `python-chess` only. Nothing else is installed.
- **No** network, file I/O, multiprocessing, or `chess.engine`.

## Strategy hints

- Material counting: prefer moves that win material and avoid hanging pieces.
- Center control: d4/d5/e4/e5 are good squares.
- King safety: castle early.
- Look one ply ahead: push each candidate, evaluate, pop.
- Minimax: search 2–3 ply, but watch the 3-second clock.
- `board.legal_moves` is your loop. Iterate, score, pick the best.
