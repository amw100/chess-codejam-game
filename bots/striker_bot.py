"""Test bot — never makes a legal move. Used to verify the strike system.

Cycles through all three strike types so each path gets exercised:
  1. raise an exception
  2. return None
  3. return an illegal move

After 3 strikes it forfeits.
"""

import chess


_call = 0


def make_move(board: chess.Board) -> chess.Move:
    global _call
    _call += 1
    mode = _call % 3
    if mode == 1:
        raise RuntimeError("striker_bot: intentional crash")
    if mode == 2:
        return None
    return chess.Move.from_uci("a1a1")
