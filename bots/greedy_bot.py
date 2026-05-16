import random
import chess

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


def capture_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return PIECE_VALUES[chess.PAWN]
    piece = board.piece_at(move.to_square)
    if piece is None:
        return 0
    return PIECE_VALUES[piece.piece_type]


def make_move(board: chess.Board) -> chess.Move:
    legal = list(board.legal_moves)
    best_value = -1
    best_moves = []
    for move in legal:
        v = capture_value(board, move)
        if v > best_value:
            best_value = v
            best_moves = [move]
        elif v == best_value:
            best_moves.append(move)
    return random.choice(best_moves)
