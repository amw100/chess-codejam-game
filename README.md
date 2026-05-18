# Chess Bot Code Jam

A 2-hour, 4-team chess bot tournament. You write one function; the rest of the system runs the game and shows it on a big screen.

## Setup

```bash
pip install -r requirements.txt
```

## Run

Start the spectator server:

```bash
python server.py
```

Open <http://localhost:5050>. Pick White and Black from the dropdowns and hit **Set Sail** — the server spawns the match for you. Use **Abandon Ship** to stop a running game and **Drop Anchor** to reset.

For headless / quick local bot testing (no UI), you can still invoke the runner directly:

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

- **Time control:** Fischer — each side starts with **2 minutes** and gains **+1 second** after every successful move. A bot may spend up to its entire remaining clock on a single move.
- **Flag fall:** if your clock hits zero, you lose immediately. No material adjudication.
- **Strikes:** Raise an exception, return `None`, or return an illegal move → a random legal move is played for you and you take a strike. **3 strikes → forfeit.** (Running out of time is *not* a strike — it's an instant loss.)
- **Allowed imports:** Python stdlib and `python-chess` only. Nothing else is installed, so `import numpy` etc. will fail at load.
- **No** network, file I/O, multiprocessing, or `chess.engine`.

## Strategy hints

- **Manage your clock.** 2 minutes + 1s/move = ~3s/move over a 40-move game, but you decide where to spend it. Blitz the obvious moves, think hard in critical positions.
- Material counting: prefer moves that win material and avoid hanging pieces.
- Center control: d4/d5/e4/e5 are good squares.
- King safety: castle early.
- Look one ply ahead: push each candidate, evaluate, pop.
- Minimax: search 2–3 ply. Deeper search costs more clock — make sure the increment can pay it back.
- `board.legal_moves` is your loop. Iterate, score, pick the best.
