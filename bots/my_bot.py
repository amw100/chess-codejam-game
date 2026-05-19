import chess


def make_move(board: chess.Board) -> chess.Move:
    """
    Given the current board state, return your chosen move.

    Args:
        board: A python-chess Board object representing the current game state.
               Useful properties & methods:
               - board.legal_moves        -> iterable of all legal moves
               - board.turn               -> chess.WHITE or chess.BLACK (your color)
               - board.move_stack         -> list of all moves played so far
               - board.is_check()         -> is the current side in check?
               - board.is_capture(move)   -> does this move capture a piece?
               - board.piece_at(square)   -> get the piece on a given square
               - board.fen()              -> FEN string of the position
               See: https://python-chess.readthedocs.io/en/latest/

    Returns:
        A chess.Move object. Must be a legal move.
    """
    # --- YOUR STRATEGY HERE ---
    import random
    return random.choice(list(board.legal_moves))
