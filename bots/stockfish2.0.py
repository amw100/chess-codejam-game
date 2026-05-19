import chess
import time
import threading
import random

class ProgramTimer:
    def __init__(self):
        self.start_time = time.time()
        self.running = True

    def elapsed_time(self):
        return time.time() - self.start_time

    def display_timer(self):
        while self.running:
            elapsed = int(self.elapsed_time())

            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60

            print(
                f"\rRunning Time: {hours:02}:{minutes:02}:{seconds:02}",
                end=""
            )

            time.sleep(1)

    def stop(self):
        self.running = False

# Create timer
timer = ProgramTimer()

# Start timer in background thread
timer_thread = threading.Thread(target=timer.display_timer)
timer_thread.start()


# -------------------
# Your program here
# -------------------
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.ROOK: 2,
    chess.KNIGHT: 3,
    chess.BISHOP: 4,
    chess.QUEEN: 9,
    chess.KING: 0,
}
CENTER_SQUARES = {chess.D4, chess.D5, chess.E4, chess.E5}
KNIGHT_PREFERRED_FILES = {2, 5}  # c-file and f-file
KNIGHT_UNWANTED_FILES = {0, 7}  # a-file and h-file
REPEAT_MOVE_LIMIT = 2
repeat_counts = {}


def piece_value(piece_type: int) -> int:
    return PIECE_VALUES.get(piece_type, 0)


def categorize_move(board: chess.Board, move: chess.Move) -> bool:
    return board.is_capture(move)


def capture_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return piece_value(chess.PAWN)
    captured = board.piece_at(move.to_square)
    return piece_value(captured.piece_type) if captured else 0


def strategic_value(board: chess.Board, move: chess.Move) -> float:
    piece = board.piece_at(move.from_square)
    if piece is None:
        return 0.0

    value = piece_value(piece.piece_type) * 0.5
    if board.is_castling(move):
        value += 6.0

    if move.to_square in CENTER_SQUARES:
        value += 2.0

    if board.gives_check(move):
        value += 2.5

    if piece.piece_type in (chess.KNIGHT, chess.BISHOP):
        from_rank = chess.square_rank(move.from_square)
        to_rank = chess.square_rank(move.to_square)
        if from_rank in (0, 7) and to_rank not in (0, 7):
            value += 1.0

    if piece.piece_type == chess.KNIGHT:
        to_file = chess.square_file(move.to_square)
        if chess.square_rank(move.from_square) in (0, 7):
            if to_file in KNIGHT_PREFERRED_FILES:
                value += 2.0
            elif to_file in KNIGHT_UNWANTED_FILES:
                value -= 1.0

    board.push(move)
    mobility = len(list(board.legal_moves))
    board.pop()
    value += mobility * 0.05

    return value


def evaluate_move(board: chess.Board, move: chess.Move) -> float:
    if board.is_capture(move):
        score = capture_value(board, move) * 10.0
        if board.gives_check(move):
            score += 2.0
        return score
    return strategic_value(board, move)


def best_reply_value(board: chess.Board) -> float:
    if board.is_checkmate():
        return 1000.0
    opponent_moves = list(board.legal_moves)
    if not opponent_moves:
        return 0.0
    return max(evaluate_move(board, move) for move in opponent_moves)


def position_key(board: chess.Board) -> str:
    fen_parts = board.fen().split(' ')
    return ' '.join(fen_parts[:4])


def repetition_count(board: chess.Board, move: chess.Move) -> int:
    key = (position_key(board), move.uci())
    return repeat_counts.get(key, 0)


def record_move(board: chess.Board, move: chess.Move) -> None:
    key = (position_key(board), move.uci())
    repeat_counts[key] = repeat_counts.get(key, 0) + 1


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
    move_nb = len(board.move_stack)
    elapsed = timer.elapsed_time()
    if elapsed < 60:
        print("Less than a minute")

    legal_moves = list(board.legal_moves)
    attack_moves = []
    strategic_moves = []
    for move in legal_moves:
        if categorize_move(board, move):
            attack_moves.append(move)
        else:
            strategic_moves.append(move)

    best_score = float('-inf')
    best_moves = []

    for move in legal_moves:
        if repetition_count(board, move) >= REPEAT_MOVE_LIMIT:
            continue

        move_score = evaluate_move(board, move)

        board.push(move)
        if board.is_checkmate():
            reply_score = -1000.0
        else:
            reply_score = best_reply_value(board)
        board.pop()

        total_score = move_score - reply_score * 0.8
        if total_score > best_score:
            best_score = total_score
            best_moves = [move]
        elif total_score == best_score:
            best_moves.append(move)

    if not best_moves:
        legal_moves = [move for move in legal_moves if repetition_count(board, move) < REPEAT_MOVE_LIMIT]
        if not legal_moves:
            legal_moves = list(board.legal_moves)
        chosen_move = random.choice(legal_moves)
    else:
        chosen_move = random.choice(best_moves)

    record_move(board, chosen_move)
    return chosen_move




# Stop timer when program ends
timer.stop()
timer_thread.join()

