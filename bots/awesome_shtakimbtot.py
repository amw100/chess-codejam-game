"""
awesome_shtakimbtot.py
======================
Iterative-deepening minimax with α-β pruning.

Features
--------
• Opening book   – instant reply on known positions (saves clock)
• Adaptive time  – self-tracked clock, budget = remaining / 25 (capped at 2 s)
• Move ordering  – promotions → MVV-LVA captures → quiet moves
• Piece-square tables – positional bonuses (midgame + endgame king tables)
• Transposition table – avoid re-searching identical positions
"""

import chess
import time

# ── Piece values (centipawns) ─────────────────────────────────────────────────

PIECE_VALUES = {
    chess.PAWN:   100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK:   500,
    chess.QUEEN:  900,
    chess.KING:   20_000,
}

# ── Piece-Square Tables ───────────────────────────────────────────────────────
# Index 0 = a8, index 63 = h1  (white's perspective, rank 8 → rank 1 top-down)
# White piece on sq  → table[(7 - sq//8)*8 + sq%8]
# Black piece on sq  → table[sq]   (board already flipped)

_PAWN_PST = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]

_KNIGHT_PST = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]

_BISHOP_PST = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]

_ROOK_PST = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
]

_QUEEN_PST = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]

_KING_MID_PST = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
]

_KING_END_PST = [
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
]

_PST = {
    chess.PAWN:   _PAWN_PST,
    chess.KNIGHT: _KNIGHT_PST,
    chess.BISHOP: _BISHOP_PST,
    chess.ROOK:   _ROOK_PST,
    chess.QUEEN:  _QUEEN_PST,
    chess.KING:   _KING_MID_PST,
}


def _pst_val(sq: int, color: bool, table: list) -> int:
    idx = (7 - sq // 8) * 8 + (sq % 8) if color == chess.WHITE else sq
    return table[idx]


# ── Opening Book ──────────────────────────────────────────────────────────────
# Key: first 4 FEN fields (strip halfmove/fullmove clocks).
# Value: UCI string.

_BOOK: dict = {
    # As White
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -":             "e2e4",
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6":        "g1f3",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -":     "f1b5",
    "rnbqkbnr/ppp1pppp/8/3p4/3P4/8/PPP1PPPP/RNBQKBNR w KQkq d6":        "c2c4",
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6":        "g1f3",
    "rnbqkb1r/pppp1ppp/4pn2/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq -":        "g1f3",
    # As Black
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3":          "e7e5",
    "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq d3":          "d7d5",
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq -":       "b8c6",
    "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq -":    "a7a6",
    "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR b KQkq c3":        "e7e6",
}


def _book_move(board: chess.Board):
    key = " ".join(board.fen().split()[:4])
    uci = _BOOK.get(key)
    if uci:
        move = chess.Move.from_uci(uci)
        if move in board.legal_moves:
            return move
    return None


# ── Self-tracked clock state ──────────────────────────────────────────────────

_our_moves = 0          # successful moves we've made
_time_spent = 0.0       # cumulative wall-clock seconds we've consumed
_call_start = 0.0       # monotonic timestamp at start of current make_move call

_BASE = 120.0
_INC  = 1.0


def _estimated_remaining() -> float:
    # Remaining = base + increments earned so far - time already consumed
    return max(1.0, _BASE + _our_moves * _INC - _time_spent)


def _move_budget() -> float:
    remaining = _estimated_remaining()
    # Spend at most remaining/25 or 2 s, whichever is less
    return min(2.0, remaining / 25.0)


# ── Evaluation ────────────────────────────────────────────────────────────────

def _is_endgame(board: chess.Board) -> bool:
    q = (len(board.pieces(chess.QUEEN, chess.WHITE)) +
         len(board.pieces(chess.QUEEN, chess.BLACK)))
    if q == 0:
        return True
    minor = sum(
        len(board.pieces(pt, c))
        for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK)
        for c in (chess.WHITE, chess.BLACK)
    )
    return minor <= 2


_MATE_SCORE = 100_000


def evaluate(board: chess.Board) -> int:
    """Static eval from White's perspective (centipawns)."""
    if board.is_checkmate():
        return -_MATE_SCORE if board.turn == chess.WHITE else _MATE_SCORE
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    endgame = _is_endgame(board)
    king_table = _KING_END_PST if endgame else _KING_MID_PST
    score = 0

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None:
            continue
        pt = piece.piece_type
        table = king_table if pt == chess.KING else _PST[pt]
        val = PIECE_VALUES[pt] + _pst_val(sq, piece.color, table)
        score += val if piece.color == chess.WHITE else -val

    return score


# ── Move ordering ─────────────────────────────────────────────────────────────

def _move_score(board: chess.Board, move: chess.Move) -> int:
    """Higher = try earlier (for alpha-beta efficiency)."""
    s = 0
    # Promotion to queen
    if move.promotion == chess.QUEEN:
        s += 10_000
    # MVV-LVA: most-valuable victim, least-valuable attacker
    if board.is_capture(move):
        victim_sq = move.to_square
        if board.is_en_passant(move):
            victim_val = PIECE_VALUES[chess.PAWN]
        else:
            victim = board.piece_at(victim_sq)
            victim_val = PIECE_VALUES[victim.piece_type] if victim else 0
        attacker = board.piece_at(move.from_square)
        attacker_val = PIECE_VALUES[attacker.piece_type] if attacker else 0
        s += 1_000 + victim_val * 10 - attacker_val
    return s


def _ordered_moves(board: chess.Board):
    moves = list(board.legal_moves)
    moves.sort(key=lambda m: _move_score(board, m), reverse=True)
    return moves


# ── Transposition table ───────────────────────────────────────────────────────

# Entries: hash → (depth, flag, score, best_move)
# flag: 0=exact, 1=lower-bound (beta cut), 2=upper-bound (alpha cut)
_TT: dict = {}
_TT_MAX = 500_000   # cap memory usage


def _tt_get(key, depth, alpha, beta):
    entry = _TT.get(key)
    if entry is None:
        return None
    e_depth, e_flag, e_score, e_move = entry
    if e_depth < depth:
        return None
    if e_flag == 0:
        return e_score
    if e_flag == 1 and e_score <= alpha:
        return e_score
    if e_flag == 2 and e_score >= beta:
        return e_score
    return None


def _tt_store(key, depth, flag, score, best_move):
    if len(_TT) >= _TT_MAX:
        _TT.clear()
    _TT[key] = (depth, flag, score, best_move)


# ── Alpha-beta search ─────────────────────────────────────────────────────────

_deadline = 0.0   # monotonic time by which we must finish


def _alpha_beta(board: chess.Board, depth: int, alpha: int, beta: int) -> int:
    """Negamax alpha-beta. Returns score from the perspective of the side to move."""
    if time.monotonic() >= _deadline:
        return evaluate(board) * (1 if board.turn == chess.WHITE else -1)

    if board.is_game_over(claim_draw=True):
        if board.is_checkmate():
            return -_MATE_SCORE
        return 0

    if depth == 0:
        raw = evaluate(board)
        return raw if board.turn == chess.WHITE else -raw

    try:
        key = chess.polyglot.zobrist_hash(board)
    except Exception:
        key = board.fen()

    hit = _tt_get(key, depth, alpha, beta)
    if hit is not None:
        return hit

    orig_alpha = alpha
    best_score = -_MATE_SCORE - 1
    best_move = None

    for move in _ordered_moves(board):
        board.push(move)
        score = -_alpha_beta(board, depth - 1, -beta, -alpha)
        board.pop()

        if score > best_score:
            best_score = score
            best_move = move
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break  # beta cut-off

        if time.monotonic() >= _deadline:
            break

    flag = 0 if alpha > orig_alpha else (2 if best_score >= beta else 1)
    _tt_store(key, depth, flag, best_score, best_move)
    return best_score


def _iterative_deepening(board: chess.Board) -> chess.Move:
    """Run ID search within the time budget; return best move found."""
    global _deadline
    budget = _move_budget()
    _deadline = time.monotonic() + budget

    legal = list(board.legal_moves)
    best_move = legal[0]  # fallback: always have a legal move ready

    for depth in range(1, 7):
        if time.monotonic() >= _deadline:
            break

        # Root-level negamax: pick best child
        alpha = -_MATE_SCORE - 1
        beta  =  _MATE_SCORE + 1
        depth_best = None
        depth_score = -_MATE_SCORE - 1

        for move in _ordered_moves(board):
            if time.monotonic() >= _deadline:
                break
            board.push(move)
            score = -_alpha_beta(board, depth - 1, -beta, -alpha)
            board.pop()

            if score > depth_score:
                depth_score = score
                depth_best = move
            if score > alpha:
                alpha = score

        if depth_best is not None:
            best_move = depth_best

        # If we found a mate, no need to search deeper
        if depth_score >= _MATE_SCORE - 100:
            break

    return best_move


# ── Public API ────────────────────────────────────────────────────────────────

def make_move(board: chess.Board) -> chess.Move:
    global _our_moves, _time_spent, _call_start

    _call_start = time.monotonic()

    try:
        # 1. Opening book (free move — costs ~0 ms, earns full increment)
        book = _book_move(board)
        if book is not None:
            _our_moves += 1
            _time_spent += time.monotonic() - _call_start
            return book

        # 2. Iterative-deepening alpha-beta
        move = _iterative_deepening(board)

        # Sanity-check: must be a legal move
        if move not in board.legal_moves:
            move = next(iter(board.legal_moves))

        _our_moves += 1
        _time_spent += time.monotonic() - _call_start
        return move

    except Exception:
        # Last-resort: never raise, never return None
        _time_spent += time.monotonic() - _call_start
        return next(iter(board.legal_moves))
