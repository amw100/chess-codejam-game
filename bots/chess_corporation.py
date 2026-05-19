from time import perf_counter


PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6
WHITE, BLACK = True, False

INF = 1_000_000_000
MATE = 100_000
MAX_PLY = 128
TT_LIMIT = 350_000

MG_VALUE = (0, 100, 320, 335, 500, 930, 0)
EG_VALUE = (0, 120, 305, 335, 510, 930, 0)
PHASE_VALUE = (0, 0, 1, 1, 2, 4, 0)
MOBILITY = (0, 0, 4, 4, 2, 1, 0)
PROMOTION_BONUS = (0, 0, 280, 290, 470, 850, 0)

EXACT, LOWER, UPPER = 0, 1, 2

_TT = {}
_KILLERS = [[None, None] for _ in range(MAX_PLY)]
_HISTORY = {}
_SPENT = {WHITE: 0.0, BLACK: 0.0}
_DEADLINE = 0.0
_NODES = 0

_START_BOARD = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"

_BOOK = {
    (): ("e2e4", "d2d4", "g1f3"),
    ("e2e4",): ("c7c5", "e7e5", "e7e6"),
    ("d2d4",): ("g8f6", "d7d5"),
    ("g1f3",): ("d7d5", "g8f6"),
    ("c2c4",): ("g8f6", "e7e5"),
    ("e2e4", "e7e5"): ("g1f3",),
    ("e2e4", "c7c5"): ("g1f3",),
    ("e2e4", "e7e6"): ("d2d4",),
    ("e2e4", "c7c6"): ("d2d4",),
    ("e2e4", "d7d5"): ("e4d5",),
    ("e2e4", "g8f6"): ("e4e5",),
    ("d2d4", "g8f6"): ("c2c4",),
    ("d2d4", "d7d5"): ("c2c4",),
    ("e2e4", "e7e5", "g1f3"): ("b8c6", "g8f6"),
    ("e2e4", "c7c5", "g1f3"): ("d7d6", "b8c6"),
    ("d2d4", "g8f6", "c2c4"): ("e7e6", "g7g6"),
    ("d2d4", "d7d5", "c2c4"): ("e7e6", "c7c6"),
    ("e2e4", "e7e5", "g1f3", "b8c6"): ("f1b5",),
    ("e2e4", "e7e5", "g1f3", "g8f6"): ("f3e5",),
    ("e2e4", "c7c5", "g1f3", "d7d6"): ("d2d4",),
    ("e2e4", "c7c5", "g1f3", "b8c6"): ("d2d4",),
}


def _pst(rows):
    table = []
    for row in reversed(rows):
        table.extend(row)
    return tuple(table)


PAWN_MG = _pst((
    (0, 0, 0, 0, 0, 0, 0, 0),
    (50, 50, 50, 50, 50, 50, 50, 50),
    (10, 10, 20, 30, 30, 20, 10, 10),
    (5, 5, 10, 25, 25, 10, 5, 5),
    (0, 0, 0, 20, 20, 0, 0, 0),
    (5, -5, -10, 0, 0, -10, -5, 5),
    (5, 10, 10, -20, -20, 10, 10, 5),
    (0, 0, 0, 0, 0, 0, 0, 0),
))

PAWN_EG = _pst((
    (0, 0, 0, 0, 0, 0, 0, 0),
    (85, 85, 85, 85, 85, 85, 85, 85),
    (55, 55, 55, 60, 60, 55, 55, 55),
    (35, 35, 40, 45, 45, 40, 35, 35),
    (20, 20, 25, 30, 30, 25, 20, 20),
    (10, 10, 10, 15, 15, 10, 10, 10),
    (5, 5, 5, -10, -10, 5, 5, 5),
    (0, 0, 0, 0, 0, 0, 0, 0),
))

KNIGHT_MG = _pst((
    (-50, -40, -30, -30, -30, -30, -40, -50),
    (-40, -20, 0, 5, 5, 0, -20, -40),
    (-30, 5, 10, 15, 15, 10, 5, -30),
    (-30, 0, 15, 25, 25, 15, 0, -30),
    (-30, 5, 15, 25, 25, 15, 5, -30),
    (-30, 0, 10, 15, 15, 10, 0, -30),
    (-40, -20, 0, 0, 0, 0, -20, -40),
    (-50, -40, -30, -30, -30, -30, -40, -50),
))

KNIGHT_EG = _pst((
    (-45, -30, -25, -25, -25, -25, -30, -45),
    (-30, -15, 0, 5, 5, 0, -15, -30),
    (-25, 5, 15, 20, 20, 15, 5, -25),
    (-25, 10, 20, 25, 25, 20, 10, -25),
    (-25, 10, 20, 25, 25, 20, 10, -25),
    (-25, 5, 15, 20, 20, 15, 5, -25),
    (-30, -15, 0, 5, 5, 0, -15, -30),
    (-45, -30, -25, -25, -25, -25, -30, -45),
))

BISHOP_MG = _pst((
    (-20, -10, -10, -10, -10, -10, -10, -20),
    (-10, 5, 0, 0, 0, 0, 5, -10),
    (-10, 10, 10, 10, 10, 10, 10, -10),
    (-10, 0, 10, 15, 15, 10, 0, -10),
    (-10, 5, 5, 15, 15, 5, 5, -10),
    (-10, 0, 5, 10, 10, 5, 0, -10),
    (-10, 0, 0, 0, 0, 0, 0, -10),
    (-20, -10, -10, -10, -10, -10, -10, -20),
))

BISHOP_EG = _pst((
    (-15, -5, -5, -5, -5, -5, -5, -15),
    (-5, 10, 5, 5, 5, 5, 10, -5),
    (-5, 10, 15, 15, 15, 15, 10, -5),
    (-5, 5, 15, 20, 20, 15, 5, -5),
    (-5, 5, 15, 20, 20, 15, 5, -5),
    (-5, 10, 15, 15, 15, 15, 10, -5),
    (-5, 10, 5, 5, 5, 5, 10, -5),
    (-15, -5, -5, -5, -5, -5, -5, -15),
))

ROOK_MG = _pst((
    (0, 0, 0, 5, 5, 0, 0, 0),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (5, 10, 10, 10, 10, 10, 10, 5),
    (0, 0, 0, 0, 0, 0, 0, 0),
))

ROOK_EG = _pst((
    (5, 5, 5, 10, 10, 5, 5, 5),
    (5, 10, 10, 10, 10, 10, 10, 5),
    (0, 5, 5, 5, 5, 5, 5, 0),
    (0, 5, 5, 5, 5, 5, 5, 0),
    (0, 5, 5, 5, 5, 5, 5, 0),
    (0, 5, 5, 5, 5, 5, 5, 0),
    (0, 5, 5, 5, 5, 5, 5, 0),
    (0, 0, 0, 5, 5, 0, 0, 0),
))

QUEEN_MG = _pst((
    (-20, -10, -10, -5, -5, -10, -10, -20),
    (-10, 0, 0, 0, 0, 0, 0, -10),
    (-10, 0, 5, 5, 5, 5, 0, -10),
    (-5, 0, 5, 5, 5, 5, 0, -5),
    (0, 0, 5, 5, 5, 5, 0, -5),
    (-10, 5, 5, 5, 5, 5, 0, -10),
    (-10, 0, 5, 0, 0, 0, 0, -10),
    (-20, -10, -10, -5, -5, -10, -10, -20),
))

QUEEN_EG = _pst((
    (-10, -5, -5, 0, 0, -5, -5, -10),
    (-5, 0, 5, 5, 5, 5, 0, -5),
    (-5, 5, 10, 10, 10, 10, 5, -5),
    (0, 5, 10, 15, 15, 10, 5, 0),
    (0, 5, 10, 15, 15, 10, 5, 0),
    (-5, 5, 10, 10, 10, 10, 5, -5),
    (-5, 0, 5, 5, 5, 5, 0, -5),
    (-10, -5, -5, 0, 0, -5, -5, -10),
))

KING_MG = _pst((
    (-30, -40, -40, -50, -50, -40, -40, -30),
    (-30, -40, -40, -50, -50, -40, -40, -30),
    (-30, -40, -40, -50, -50, -40, -40, -30),
    (-30, -40, -40, -50, -50, -40, -40, -30),
    (-20, -30, -30, -40, -40, -30, -30, -20),
    (-10, -20, -20, -20, -20, -20, -20, -10),
    (20, 20, 0, 0, 0, 0, 20, 20),
    (20, 30, 10, 0, 0, 10, 30, 20),
))

KING_EG = _pst((
    (-50, -30, -30, -30, -30, -30, -30, -50),
    (-30, -10, 0, 0, 0, 0, -10, -30),
    (-30, 0, 10, 15, 15, 10, 0, -30),
    (-30, 0, 15, 25, 25, 15, 0, -30),
    (-30, 0, 15, 25, 25, 15, 0, -30),
    (-30, 0, 10, 15, 15, 10, 0, -30),
    (-30, -10, 0, 0, 0, 0, -10, -30),
    (-50, -30, -30, -30, -30, -30, -30, -50),
))

MG_TABLES = ((), PAWN_MG, KNIGHT_MG, BISHOP_MG, ROOK_MG, QUEEN_MG, KING_MG)
EG_TABLES = ((), PAWN_EG, KNIGHT_EG, BISHOP_EG, ROOK_EG, QUEEN_EG, KING_EG)

PASSED_MG = (0, 5, 15, 30, 55, 95, 160, 0)
PASSED_EG = (0, 10, 25, 50, 90, 150, 240, 0)
CENTER = {27, 28, 35, 36}
BIG_CENTER = {18, 19, 20, 21, 26, 27, 28, 29, 34, 35, 36, 37, 42, 43, 44, 45}


class _SearchTimeout(Exception):
    pass


def make_move(board):
    """
    Return a legal move for the supplied python-chess Board.

    The implementation intentionally imports no third-party package. It only
    uses the Board and Move objects handed to it by the tournament runner.
    """
    start = perf_counter()
    color = board.turn
    legal = list(board.legal_moves)
    if not legal:
        return None

    fallback = _fallback_move(board, legal)
    if len(legal) == 1:
        _record_time(color, start)
        return legal[0]

    try:
        mate = _mate_in_one(board, legal)
        if mate is not None:
            return mate

        book = _book_move(board, legal)
        if book is not None:
            return book

        budget = _time_budget(board, len(legal))
        global _DEADLINE, _NODES
        _DEADLINE = start + budget
        _NODES = 0

        best_move = fallback
        best_score = -INF
        depth = 1
        while depth <= 64:
            if perf_counter() + 0.004 >= _DEADLINE:
                break
            try:
                if depth >= 4 and best_score > -INF // 2:
                    window = 45
                    score, move = _root_search(
                        board, legal, depth, best_score - window, best_score + window, best_move
                    )
                    if score <= best_score - window or score >= best_score + window:
                        score, move = _root_search(board, legal, depth, -INF, INF, best_move)
                else:
                    score, move = _root_search(board, legal, depth, -INF, INF, best_move)
            except _SearchTimeout:
                break

            if move in legal:
                best_move = move
                best_score = score
            if best_score >= MATE - 200:
                break
            depth += 1

        return best_move if best_move in legal else fallback
    except Exception:
        return fallback
    finally:
        _record_time(color, start)
        if len(_TT) > TT_LIMIT:
            _TT.clear()


def _record_time(color, start):
    _SPENT[color] = _SPENT.get(color, 0.0) + max(0.0, perf_counter() - start)


def _time_budget(board, legal_count):
    own_moves = len(board.move_stack) // 2
    remaining = 120.0 + own_moves - _SPENT.get(board.turn, 0.0)

    if remaining <= 1.0:
        return 0.02
    if remaining < 8.0:
        return min(0.18, max(0.03, remaining * 0.08))
    if remaining < 25.0:
        return min(0.38, max(0.08, remaining * 0.06))
    if remaining < 55.0:
        return min(0.80, max(0.18, remaining * 0.05))

    if own_moves < 8:
        target = 0.70
    elif own_moves < 35:
        target = 1.15
    else:
        target = 0.90

    target += min(0.55, legal_count * 0.012)
    if board.is_check():
        target += 0.20
    if legal_count <= 10:
        target += 0.20

    reserve = 7.0
    cap = max(0.05, (remaining - reserve) * 0.075)
    return min(target, cap, 1.85)


def _book_move(board, legal):
    if len(board.move_stack) > 6:
        return None
    if not board.move_stack and board.board_fen() != _START_BOARD:
        return None

    history = tuple(move.uci() for move in board.move_stack)
    candidates = _BOOK.get(history)
    if not candidates:
        return None

    by_uci = {move.uci(): move for move in legal}
    for uci in candidates:
        move = by_uci.get(uci)
        if move is not None:
            return move
    return None


def _mate_in_one(board, legal):
    for move in legal:
        board.push(move)
        try:
            if board.is_checkmate():
                return move
        finally:
            board.pop()
    return None


def _fallback_move(board, legal):
    best = legal[0]
    best_score = -INF
    for move in legal:
        score = _quick_move_score(board, move)
        if score > best_score:
            best_score = score
            best = move
    return best


def _root_search(board, legal, depth, alpha, beta, previous_best):
    ordered = sorted(
        legal,
        key=lambda move: _move_score(board, move, previous_best, 0),
        reverse=True,
    )
    best_move = ordered[0]
    best_score = -INF

    for index, move in enumerate(ordered):
        _check_time()
        board.push(move)
        try:
            if index == 0:
                score = -_search(board, depth - 1, -beta, -alpha, 1)
            else:
                score = -_search(board, depth - 1, -alpha - 1, -alpha, 1)
                if alpha < score < beta:
                    score = -_search(board, depth - 1, -beta, -alpha, 1)
        finally:
            board.pop()

        if score > best_score:
            best_score = score
            best_move = move
        if score > alpha:
            alpha = score
        if alpha >= beta:
            if not _is_tactical(board, move):
                _remember_quiet(move, depth, 0)
            break

    return best_score, best_move


def _search(board, depth, alpha, beta, ply):
    _check_time()

    if board.halfmove_clock >= 100 or board.is_insufficient_material():
        return 0

    in_check = board.is_check()
    if depth <= 0 and not in_check:
        return _quiescence(board, alpha, beta, ply)
    if in_check and depth <= 0:
        depth = 1

    key = board._transposition_key()
    entry = _TT.get(key)
    tt_move = None
    if entry is not None:
        entry_depth, flag, score, move = entry
        tt_move = move
        if entry_depth >= depth:
            if flag == EXACT:
                return score
            if flag == LOWER and score > alpha:
                alpha = score
            elif flag == UPPER and score < beta:
                beta = score
            if alpha >= beta:
                return score

    legal = list(board.legal_moves)
    if not legal:
        return -MATE + ply if in_check else 0

    legal.sort(key=lambda move: _move_score(board, move, tt_move, ply), reverse=True)

    original_alpha = alpha
    best_score = -INF
    best_move = legal[0]

    for index, move in enumerate(legal):
        quiet = not _is_tactical(board, move)
        board.push(move)
        try:
            gives_check = board.is_check()
            extension = 1 if gives_check and depth <= 2 and ply < 8 else 0
            next_depth = depth - 1 + extension

            reduction = 0
            if (
                index >= 4
                and depth >= 3
                and quiet
                and not in_check
                and not gives_check
            ):
                reduction = 1
                if index >= 10 and depth >= 5:
                    reduction = 2

            search_depth = max(0, next_depth - reduction)
            if index == 0:
                score = -_search(board, next_depth, -beta, -alpha, ply + 1)
            else:
                score = -_search(board, search_depth, -alpha - 1, -alpha, ply + 1)
                if score > alpha and reduction:
                    score = -_search(board, next_depth, -alpha - 1, -alpha, ply + 1)
                if alpha < score < beta:
                    score = -_search(board, next_depth, -beta, -alpha, ply + 1)
        finally:
            board.pop()

        if score > best_score:
            best_score = score
            best_move = move
        if score > alpha:
            alpha = score
        if alpha >= beta:
            if quiet:
                _remember_quiet(move, depth, ply)
            break

    if best_score <= original_alpha:
        flag = UPPER
    elif best_score >= beta:
        flag = LOWER
    else:
        flag = EXACT
    _TT[key] = (depth, flag, best_score, best_move)
    return best_score


def _quiescence(board, alpha, beta, ply):
    _check_time()

    if board.halfmove_clock >= 100 or board.is_insufficient_material():
        return 0
    if board.is_check():
        return _search(board, 1, alpha, beta, ply)

    stand_pat = _evaluate(board)
    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat
    if ply >= 18:
        return alpha

    moves = []
    for move in board.legal_moves:
        if board.is_capture(move) or move.promotion:
            moves.append(move)

    moves.sort(key=lambda move: _capture_score(board, move), reverse=True)

    for move in moves:
        swing = _capture_value(board, move)
        if not move.promotion and stand_pat + swing + 160 < alpha:
            continue
        board.push(move)
        try:
            score = -_quiescence(board, -beta, -alpha, ply + 1)
        finally:
            board.pop()

        if score >= beta:
            return beta
        if score > alpha:
            alpha = score
    return alpha


def _evaluate(board):
    if board.is_insufficient_material():
        return 0

    mg = 0
    eg = 0
    phase = 0
    bishops = [0, 0]
    pawn_files = [[0] * 8, [0] * 8]
    pawn_ranks = [[0] * 8, [0] * 8]
    pawns = []
    rooks = []
    kings = [None, None]

    for square, piece in board.piece_map().items():
        color = piece.color
        piece_type = piece.piece_type
        sign = 1 if color == WHITE else -1
        view_square = square if color == WHITE else square ^ 56

        mg += sign * (MG_VALUE[piece_type] + MG_TABLES[piece_type][view_square])
        eg += sign * (EG_VALUE[piece_type] + EG_TABLES[piece_type][view_square])
        phase += PHASE_VALUE[piece_type]

        if piece_type == PAWN:
            file_index = square & 7
            rank_index = square >> 3
            pawn_files[color][file_index] += 1
            pawn_ranks[color][file_index] |= 1 << rank_index
            pawns.append((square, color))
        elif piece_type == BISHOP:
            bishops[color] += 1
            mobility = board.attacks_mask(square).bit_count() * MOBILITY[BISHOP]
            mg += sign * mobility
            eg += sign * (mobility // 2)
        elif piece_type == KNIGHT:
            mobility = board.attacks_mask(square).bit_count() * MOBILITY[KNIGHT]
            mg += sign * mobility
            eg += sign * (mobility // 2)
        elif piece_type == ROOK:
            rooks.append((square, color))
            mobility = board.attacks_mask(square).bit_count() * MOBILITY[ROOK]
            mg += sign * mobility
            eg += sign * mobility
        elif piece_type == QUEEN:
            mobility = board.attacks_mask(square).bit_count() * MOBILITY[QUEEN]
            mg += sign * mobility
            eg += sign * mobility
        elif piece_type == KING:
            kings[color] = square

    if bishops[WHITE] >= 2:
        mg += 35
        eg += 45
    if bishops[BLACK] >= 2:
        mg -= 35
        eg -= 45

    for color in (BLACK, WHITE):
        sign = 1 if color == WHITE else -1
        enemy = not color
        for file_index, count in enumerate(pawn_files[color]):
            if count > 1:
                penalty = 12 * (count - 1)
                mg -= sign * penalty
                eg -= sign * (penalty // 2)
            if count and _adjacent_pawns(pawn_files[color], file_index) == 0:
                penalty = 9 * count
                mg -= sign * penalty
                eg -= sign * (penalty // 2)

        for square, pawn_color in pawns:
            if pawn_color != color:
                continue
            file_index = square & 7
            rank_index = square >> 3
            if _is_passed_pawn(color, file_index, rank_index, pawn_ranks[enemy]):
                advanced = rank_index if color == WHITE else 7 - rank_index
                bonus_mg = PASSED_MG[advanced]
                bonus_eg = PASSED_EG[advanced]
                mg += sign * bonus_mg
                eg += sign * bonus_eg

    for square, color in rooks:
        file_index = square & 7
        sign = 1 if color == WHITE else -1
        friendly_pawns = pawn_files[color][file_index]
        enemy_pawns = pawn_files[not color][file_index]
        if friendly_pawns == 0 and enemy_pawns == 0:
            mg += sign * 22
            eg += sign * 14
        elif friendly_pawns == 0:
            mg += sign * 12
            eg += sign * 8

    if phase > 8:
        mg += _king_safety_score(WHITE, kings[WHITE], pawn_files, pawn_ranks)
        mg -= _king_safety_score(BLACK, kings[BLACK], pawn_files, pawn_ranks)

    phase = min(24, phase)
    score = (mg * phase + eg * (24 - phase)) // 24
    score += 8 if board.turn == WHITE else -8
    return score if board.turn == WHITE else -score


def _king_safety_score(color, king_square, pawn_files, pawn_ranks):
    if king_square is None:
        return 0

    file_index = king_square & 7
    score = 0
    for shield_file in range(max(0, file_index - 1), min(8, file_index + 2)):
        ranks = pawn_ranks[color][shield_file]
        if color == WHITE:
            if ranks & (1 << 1):
                score += 8
            if ranks & (1 << 2):
                score += 4
        else:
            if ranks & (1 << 6):
                score += 8
            if ranks & (1 << 5):
                score += 4

    if pawn_files[color][file_index] == 0:
        score -= 16
    if king_square in CENTER:
        score -= 28
    return score


def _adjacent_pawns(files, file_index):
    count = 0
    if file_index > 0:
        count += files[file_index - 1]
    if file_index < 7:
        count += files[file_index + 1]
    return count


def _is_passed_pawn(color, file_index, rank_index, enemy_ranks):
    for file_to_check in range(max(0, file_index - 1), min(8, file_index + 2)):
        mask = enemy_ranks[file_to_check]
        if color == WHITE:
            if mask & ~((1 << (rank_index + 1)) - 1):
                return False
        else:
            if mask & ((1 << rank_index) - 1):
                return False
    return True


def _check_time():
    global _NODES
    _NODES += 1
    if (_NODES & 2047) == 0 and perf_counter() >= _DEADLINE:
        raise _SearchTimeout


def _is_tactical(board, move):
    return board.is_capture(move) or move.promotion is not None


def _remember_quiet(move, depth, ply):
    if ply < MAX_PLY:
        first, second = _KILLERS[ply]
        if move != first:
            _KILLERS[ply][1] = first if second != move else second
            _KILLERS[ply][0] = move
    key = _move_key(move)
    _HISTORY[key] = min(50_000, _HISTORY.get(key, 0) + depth * depth)


def _move_key(move):
    return (move.from_square, move.to_square, move.promotion or 0)


def _move_score(board, move, tt_move, ply):
    if tt_move is not None and move == tt_move:
        return 50_000_000

    score = _quick_move_score(board, move)
    if not board.is_capture(move) and move.promotion is None:
        if ply < MAX_PLY:
            if move == _KILLERS[ply][0]:
                score += 900_000
            elif move == _KILLERS[ply][1]:
                score += 800_000
        score += _HISTORY.get(_move_key(move), 0)
    return score


def _quick_move_score(board, move):
    moving = board.piece_at(move.from_square)
    score = 0

    if board.is_capture(move):
        score += 1_000_000 + _capture_score(board, move)
    if move.promotion:
        score += 900_000 + PROMOTION_BONUS[move.promotion]
    if moving is not None:
        piece_type = moving.piece_type
        color = moving.color
        from_square = move.from_square if color == WHITE else move.from_square ^ 56
        to_square = move.to_square if color == WHITE else move.to_square ^ 56
        score += (MG_TABLES[piece_type][to_square] - MG_TABLES[piece_type][from_square]) * 3
        if piece_type in (KNIGHT, BISHOP) and move.to_square in BIG_CENTER:
            score += 40
        elif move.to_square in CENTER:
            score += 24
    if board.is_castling(move):
        score += 70_000
    return score


def _capture_score(board, move):
    victim_value = _capture_value(board, move)
    attacker = board.piece_at(move.from_square)
    attacker_value = MG_VALUE[attacker.piece_type] if attacker is not None else 0
    return victim_value * 10 - attacker_value


def _capture_value(board, move):
    if board.is_en_passant(move):
        victim = PAWN
    else:
        victim_piece = board.piece_at(move.to_square)
        victim = victim_piece.piece_type if victim_piece is not None else 0
    value = MG_VALUE[victim]
    if move.promotion:
        value += PROMOTION_BONUS[move.promotion]
    return value
