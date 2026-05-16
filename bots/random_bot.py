import random
import chess


def make_move(board: chess.Board) -> chess.Move:
    return random.choice(list(board.legal_moves))
