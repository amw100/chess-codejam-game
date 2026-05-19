import chess
import chess.polyglot
import time
import random

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}
MATE = 100000
INF = 1 << 30

PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]
KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]
BISHOP_TABLE = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]
ROOK_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
]
QUEEN_TABLE = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]
KING_MID_TABLE = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
]
KING_END_TABLE = [
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
]

# Pre-compute PST[piece_type][color][square] so eval avoids per-piece indexing math
def _build_pst_lookup():
    base = {
        chess.PAWN:   PAWN_TABLE,
        chess.KNIGHT: KNIGHT_TABLE,
        chess.BISHOP: BISHOP_TABLE,
        chess.ROOK:   ROOK_TABLE,
        chess.QUEEN:  QUEEN_TABLE,
        chess.KING:   KING_MID_TABLE,
    }

    def square_to_idx(sq, color):
        s = sq if color == chess.WHITE else chess.square_mirror(sq)
        return (7 - chess.square_rank(s)) * 8 + chess.square_file(s)

    lookup = {}
    for pt, table in base.items():
        lookup[(pt, chess.WHITE)] = [table[square_to_idx(sq, chess.WHITE)] for sq in chess.SQUARES]
        lookup[(pt, chess.BLACK)] = [table[square_to_idx(sq, chess.BLACK)] for sq in chess.SQUARES]
    lookup[(chess.KING, chess.WHITE, True)] = [KING_END_TABLE[square_to_idx(sq, chess.WHITE)] for sq in chess.SQUARES]
    lookup[(chess.KING, chess.BLACK, True)] = [KING_END_TABLE[square_to_idx(sq, chess.BLACK)] for sq in chess.SQUARES]
    return lookup


PST_LOOKUP = _build_pst_lookup()


def _is_endgame(board):
    if not board.queens:
        return True
    minors = chess.popcount(board.knights | board.bishops)
    rooks = chess.popcount(board.rooks)
    return chess.popcount(board.queens) <= 2 and (rooks + minors) <= 3


def _evaluate(board):
    """Static eval in centipawns, from side-to-move's perspective."""
    endgame = _is_endgame(board)
    score = 0
    for pt in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        val = PIECE_VALUES[pt]
        w_table = PST_LOOKUP[(pt, chess.WHITE)]
        b_table = PST_LOOKUP[(pt, chess.BLACK)]
        for sq in board.pieces(pt, chess.WHITE):
            score += val + w_table[sq]
        for sq in board.pieces(pt, chess.BLACK):
            score -= val + b_table[sq]

    # King — pick PST based on phase
    if endgame:
        w_kt = PST_LOOKUP[(chess.KING, chess.WHITE, True)]
        b_kt = PST_LOOKUP[(chess.KING, chess.BLACK, True)]
    else:
        w_kt = PST_LOOKUP[(chess.KING, chess.WHITE)]
        b_kt = PST_LOOKUP[(chess.KING, chess.BLACK)]
    for sq in board.pieces(chess.KING, chess.WHITE):
        score += w_kt[sq]
    for sq in board.pieces(chess.KING, chess.BLACK):
        score -= b_kt[sq]

    return score if board.turn == chess.WHITE else -score


def _capture_value(board, move):
    """MVV-LVA score for a capture (assumes move is a capture)."""
    if board.is_en_passant(move):
        return 10 * PIECE_VALUES[chess.PAWN] - PIECE_VALUES[chess.PAWN]
    victim = board.piece_type_at(move.to_square)
    attacker = board.piece_type_at(move.from_square)
    if victim is None or attacker is None:
        return 0
    return 10 * PIECE_VALUES[victim] - PIECE_VALUES[attacker]


class _SearchState:
    __slots__ = ("tt", "killers", "history", "deadline", "nodes")

    def __init__(self, deadline):
        self.tt = {}  # key -> (depth, score, flag, best_move)
        self.killers = [[None, None] for _ in range(96)]
        self.history = {}
        self.deadline = deadline
        self.nodes = 0


# TT flags
TT_EXACT = 0
TT_LOWER = 1
TT_UPPER = 2


def _order_moves(board, moves, state, ply, tt_move):
    """Score moves for ordering: TT > captures (MVV-LVA) > promotions > killers > history."""
    scored = []
    if 0 <= ply < len(state.killers):
        k1, k2 = state.killers[ply]
    else:
        k1 = k2 = None

    for m in moves:
        if m == tt_move:
            s = 10_000_000
        elif board.is_capture(m):
            s = 1_000_000 + _capture_value(board, m)
        elif m.promotion:
            s = 900_000 + PIECE_VALUES[m.promotion]
        elif m == k1:
            s = 800_000
        elif m == k2:
            s = 790_000
        else:
            s = state.history.get((m.from_square, m.to_square), 0)
        scored.append((s, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


def _quiesce(board, alpha, beta, state):
    if time.time() > state.deadline:
        raise TimeoutError
    state.nodes += 1

    stand_pat = _evaluate(board)
    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat

    # Only generate captures + promotions for quiescence
    noisy = []
    for m in board.legal_moves:
        if board.is_capture(m) or m.promotion:
            noisy.append(m)
    noisy.sort(
        key=lambda m: _capture_value(board, m) if board.is_capture(m) else PIECE_VALUES.get(m.promotion, 0),
        reverse=True,
    )

    for move in noisy:
        # Delta pruning: skip clearly losing captures
        if board.is_capture(move) and not move.promotion:
            victim_pt = chess.PAWN if board.is_en_passant(move) else board.piece_type_at(move.to_square)
            if victim_pt is not None and stand_pat + PIECE_VALUES[victim_pt] + 200 < alpha:
                continue
        board.push(move)
        try:
            score = -_quiesce(board, -beta, -alpha, state)
        finally:
            board.pop()
        if score >= beta:
            return beta
        if score > alpha:
            alpha = score
    return alpha


def _alphabeta(board, depth, alpha, beta, state, ply):
    if time.time() > state.deadline:
        raise TimeoutError
    state.nodes += 1

    alpha_orig = alpha

    # TT probe
    key = chess.polyglot.zobrist_hash(board)
    tt_entry = state.tt.get(key)
    tt_move = None
    if tt_entry is not None:
        tt_depth, tt_score, tt_flag, tt_move = tt_entry
        if tt_depth >= depth:
            if tt_flag == TT_EXACT:
                return tt_score
            if tt_flag == TT_LOWER and tt_score > alpha:
                alpha = tt_score
            elif tt_flag == TT_UPPER and tt_score < beta:
                beta = tt_score
            if alpha >= beta:
                return tt_score

    in_check = board.is_check()

    # Generate legal moves once
    moves = list(board.legal_moves)
    if not moves:
        return -MATE + ply if in_check else 0

    # Check extension: search one ply deeper when in check
    if in_check:
        depth += 1

    if depth <= 0:
        return _quiesce(board, alpha, beta, state)

    # Null move pruning — skip when in check, in endgame, or shallow
    if (
        depth >= 3
        and not in_check
        and not _is_endgame(board)
        and any(board.pieces(pt, board.turn) for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN))
    ):
        board.push(chess.Move.null())
        try:
            null_score = -_alphabeta(board, depth - 3, -beta, -beta + 1, state, ply + 1)
        finally:
            board.pop()
        if null_score >= beta:
            return beta

    ordered = _order_moves(board, moves, state, ply, tt_move)

    best_score = -INF
    best_move = ordered[0]
    move_count = 0

    for move in ordered:
        move_count += 1
        is_capture = board.is_capture(move)
        is_promotion = bool(move.promotion)

        board.push(move)
        try:
            # Late move reduction — search likely-bad moves at reduced depth
            if (
                depth >= 3
                and move_count >= 4
                and not is_capture
                and not is_promotion
                and not in_check
                and not board.is_check()
            ):
                score = -_alphabeta(board, depth - 2, -alpha - 1, -alpha, state, ply + 1)
                if score > alpha:
                    score = -_alphabeta(board, depth - 1, -beta, -alpha, state, ply + 1)
            else:
                score = -_alphabeta(board, depth - 1, -beta, -alpha, state, ply + 1)
        finally:
            board.pop()

        if score > best_score:
            best_score = score
            best_move = move
        if score > alpha:
            alpha = score
        if alpha >= beta:
            # Killer + history update for quiet moves
            if not is_capture and not is_promotion:
                if 0 <= ply < len(state.killers):
                    k = state.killers[ply]
                    if k[0] != move:
                        state.killers[ply][1] = k[0]
                        state.killers[ply][0] = move
                hk = (move.from_square, move.to_square)
                state.history[hk] = state.history.get(hk, 0) + depth * depth
            break

    # TT store
    if best_score <= alpha_orig:
        flag = TT_UPPER
    elif best_score >= beta:
        flag = TT_LOWER
    else:
        flag = TT_EXACT
    state.tt[key] = (depth, best_score, flag, best_move)

    return best_score


def _repetition_penalty(board, move):
    board.push(move)
    try:
        if board.is_repetition(3):
            return 400
        if board.is_repetition(2):
            return 80
    finally:
        board.pop()
    return 0


def _time_budget(board):
    """Fischer time control: 120s + 1s/move. Self-budget by phase since we
    can't see the actual clock. Targets must stay below the per-move increment
    plus a slow drain of the starting bank so we never flag in long games."""
    move_num = board.fullmove_number
    if move_num <= 4:
        return 1.0      # opening — natural moves, no need to think long
    if move_num <= 30:
        return 2.2      # middlegame — most tactics live here
    return 1.5          # endgame — fewer pieces, simpler decisions


def make_move(board: chess.Board) -> chess.Move:
    state = _SearchState(deadline=time.time() + _time_budget(board))
    legal = list(board.legal_moves)

    if len(legal) == 1:
        return legal[0]

    shuffle = {m: _repetition_penalty(board, m) for m in legal}

    # Initial fallback: best capture or first legal move
    best_move = max(
        legal,
        key=lambda m: (
            (1 if board.is_capture(m) else 0) * 10_000
            + (_capture_value(board, m) if board.is_capture(m) else 0)
            - shuffle[m]
        ),
    )
    pv_move = None

    for depth in range(1, 64):
        if time.time() > state.deadline - 0.05:
            break
        try:
            ordered = _order_moves(board, legal, state, 0, pv_move)
            scored = []
            alpha = -INF
            beta = INF

            for move in ordered:
                board.push(move)
                try:
                    raw = -_alphabeta(board, depth - 1, -beta, -alpha, state, 1)
                finally:
                    board.pop()
                score = raw - shuffle[move]
                scored.append((score, move))
                if score > alpha:
                    alpha = score

            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                top_score = scored[0][0]
                # Only randomize on EXACT ties — keeps decisions decisive
                tied = [m for s, m in scored if s == top_score]
                best_move = random.choice(tied) if len(tied) > 1 else scored[0][1]
                pv_move = scored[0][1]
        except TimeoutError:
            break

    return best_move
