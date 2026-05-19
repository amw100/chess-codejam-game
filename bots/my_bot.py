import chess

# ─────────────────────────────────────────────
#  PIECE VALUES
# ─────────────────────────────────────────────
_PIECE_VALUES = {
    chess.PAWN:   100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK:   500,
    chess.QUEEN:  900,
    chess.KING:   20000,
}


# ─────────────────────────────────────────────
#  SCORING HELPERS
# ─────────────────────────────────────────────

def _king_safety(board: chess.Board, color: chess.Color) -> float:
    score    = 0.0
    king_sq  = board.king(color)
    if king_sq is None:
        return score

    king_file   = chess.square_file(king_sq)
    king_rank   = chess.square_rank(king_sq)
    shield_rank = king_rank + (1 if color == chess.WHITE else -1)

    # Pawn shield
    for df in (-1, 0, 1):
        f = king_file + df
        if 0 <= f <= 7 and 0 <= shield_rank <= 7:
            sq    = chess.square(f, shield_rank)
            piece = board.piece_at(sq)
            score += 30 if (piece and piece.piece_type == chess.PAWN
                            and piece.color == color) else -20

    # Open files near king
    for df in (-1, 0, 1):
        f = king_file + df
        if 0 <= f <= 7:
            if not (board.pieces(chess.PAWN, color) & chess.BB_FILES[f]):
                score -= 25

    # Enemy pieces close to king
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color != color:
            if chess.square_distance(sq, king_sq) <= 2:
                score -= _PIECE_VALUES.get(piece.piece_type, 0) * 0.05

    return score


def _piece_defense(board: chess.Board, color: chess.Color) -> float:
    score = 0.0
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == color and piece.piece_type != chess.KING:
            defs = len(board.attackers(color,     sq))
            atks = len(board.attackers(not color, sq))
            if defs == 0 and atks > 0:
                score -= _PIECE_VALUES.get(piece.piece_type, 0) * 0.8
            elif defs < atks:
                score -= _PIECE_VALUES.get(piece.piece_type, 0) * 0.3
            elif defs >= 1:
                score += 10
    return score


def _pawn_structure(board: chess.Board, color: chess.Color) -> float:
    score = 0.0
    pawns = board.pieces(chess.PAWN, color)
    files = {chess.square_file(sq) for sq in pawns}

    for sq in pawns:
        f   = chess.square_file(sq)
        r   = chess.square_rank(sq)
        adj = {f - 1, f + 1} & set(range(8))

        if not adj & files:
            score -= 30  # isolated
        if any(chess.square_file(s) == f and s != sq for s in pawns):
            score -= 20  # doubled
        support = [s for s in pawns
                   if chess.square_file(s) in adj
                   and (chess.square_rank(s) >= r
                        if color == chess.WHITE
                        else chess.square_rank(s) <= r)]
        if not support:
            score -= 15  # backward

    return score


def _weak_squares(board: chess.Board, color: chess.Color) -> float:
    score   = 0.0
    king_sq = board.king(color)
    if king_sq is None:
        return score
    for sq in chess.SQUARES:
        if chess.square_distance(sq, king_sq) <= 2:
            score += (len(board.attackers(color,     sq)) -
                      len(board.attackers(not color, sq))) * 5
    return score


def _castling_bonus(board: chess.Board, color: chess.Color) -> float:
    king_sq = board.king(color)
    if king_sq is None:
        return 0.0
    f = chess.square_file(king_sq)
    if f in (2, 6): return  60.0   # castled
    if f == 4:      return -40.0   # still on e-file
    return 0.0


def _activity(board: chess.Board, color: chess.Color) -> float:
    score = 0.0
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == color:
            score += len(board.attacks(sq)) * 1.5
    return score


# ─────────────────────────────────────────────
#  FULL DEFENSIVE EVALUATION
# ─────────────────────────────────────────────

def _evaluate(board: chess.Board, color: chess.Color) -> float:
    if board.is_checkmate():
        return -99999 if board.turn == color else 99999
    if board.is_stalemate() or board.is_insufficient_material():
        return 0.0

    return (
        _king_safety(board,    color) * 5.0 +
        _piece_defense(board,  color) * 4.0 +
        _pawn_structure(board, color) * 3.5 +
        _weak_squares(board,   color) * 3.0 +
        _activity(board,       color) * 2.0 +
        _castling_bonus(board, color)
    )



# ─────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────


def make_move_def(board: chess.Board) -> chess.Move:
    """
    Defensive strategy against a greedy opponent.

    Receives a chess.Board (any position, any side to move).
    Returns a legal chess.Move — always guaranteed to be legal.

    Scoring priorities (high -> low):
        1. King safety          (w=5.0)
        2. No hanging pieces    (w=4.0)
        3. Solid pawn structure (w=3.5)
        4. Weak square coverage (w=3.0)
        5. Piece activity       (w=2.0)
    """
    color = board.turn
    legal = list(board.legal_moves)

    best_move  = None
    best_score = -float("inf")

    for move in legal:
        board.push(move)
        score = _evaluate(board, color)
        if board.has_castling_rights(color):
            score -= 20   # small nudge to castle sooner
        board.pop()

        if score > best_score:
            best_score = score
            best_move  = move

    return best_move  # always a valid chess.Move


  

# ─────────────────────────────────────────────
#  QUICK DEMO  (greedy WHITE vs defensive BLACK)
# ─────────────────────────────────────────────

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def capture_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return PIECE_VALUES[chess.PAWN]
    piece = board.piece_at(move.to_square)
    if piece is None:
        return 0
    return PIECE_VALUES[piece.piece_type]

def make_move_atk(board: chess.Board) -> chess.Move:
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

def evaluate_board(board: chess.Board) -> int:
  """
  Returns an evaluation of the board in centipawns.
  Positive = White advantage
  Negative = Black advantage
  """
  if board.is_checkmate():
    # side to move is checkmated
    return -99999 if board.turn == chess.WHITE else 99999

  if board.is_stalemate() or board.is_insufficient_material():
    return 0

  score = 0

  for piece_type in PIECE_VALUES:
    score += len(board.pieces(piece_type, chess.WHITE)) * PIECE_VALUES[piece_type]
    score -= len(board.pieces(piece_type, chess.BLACK)) * PIECE_VALUES[piece_type]

  return score

def get_checking_move(board: chess.Board, color: chess.Color):
    """
    Returns a move that gives check for the given color.
    Returns None if no such move exists.
    """

    original_turn = board.turn
    board.turn = color

    for move in board.legal_moves:
        board.push(move)

        if board.is_check():
            board.pop()
            board.turn = original_turn
            return move

        board.pop()

    board.turn = original_turn
    return None

def make_move(board: chess.Board) -> chess.Move:
  check = get_checking_move(board, board.turn)
  if check is not None:
    return check

  advantage = evaluate_board(board)
  if board.turn == chess.BLACK:
    advantage = -1 * advantage
  
  if advantage > 0:
    return make_move_atk(board)
  
  return make_move_def(board)