class ConnectGame:
    def __init__(self, board):
        self.board = board

    def get_winner(self):
        # Check if O connects top to bottom.
        if self._check_connection('O', 'top', 'bottom'):
            return 'O'
        # Check if X connects left to right.
        if self._check_connection('X', 'left', 'right'):
            return 'X'
        return None

    def _check_connection(self, player, start, end):
        rows = len(self.board)
        cols = len(self.board[0]) if rows > 0 else 0

        # Determine start and end indices based on player and direction.
        if player == 'O':
            # O plays top to bottom: start at top row, end at bottom row.
            start_row = 0
            end_row = rows - 1
        else:
            # X plays left to right: start at leftmost column, end at rightmost column.
            start_col = 0
            end_col = cols - 1

        # Find the first cell of the player in the start position.
        start_pos = None
        if player == 'O':
            for row in range(start_row, end_row + 1):
                for col in range(cols):
                    if self.board[row][col] == player:
                        start_pos = (row, col)
                        break
                if start_pos:
                    break
        else:
            for col in range(start_col, end_col + 1):
                for row in range(rows):
                    if self.board[row][col] == player:
                        start_pos = (row, col)
                        break
                if start_pos:
                    break

        if not start_pos:
            return False

        # Traverse from start to end, checking adjacent cells.
        current_row, current_col = start_pos
        visited = set()
        visited.add((current_row, current_col))

        while True:
            # Determine next direction based on player and current position.
            if player == 'O':
                # O moves top to bottom, so we look downwards.
                next_row = current_row + 1
                next_col = current_col
            else:
                # X moves left to right, so we look rightwards.
                next_row = current_row
                next_col = current_col + 1

            # Check if we reached the end.
            if player == 'O':
                if next_row == end_row and next_col == current_col:
                    # Connected top to bottom.
                    return True
            else:
                if next_row == current_row and next_col == end_col:
                    # Connected left to right.
                    return True

            # Check if next cell is valid and contains the player.
            if (next_row, next_col) in visited:
                break
            if next_row < 0 or next_row >= rows or next_col < 0 or next_col >= cols:
                break
            if self.board[next_row][next_col] != player:
                break

            visited.add((next_row, next_col))
            current_row, current_col = next_row, next_col

        return False


if __name__ == '__main__':
    unittest.main()
