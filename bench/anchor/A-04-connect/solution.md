# A-04-connect - reference solution (never shown to a run)

Provenance: tests + instructions from exercism/python@1f6aab8667bf653b10cc3799f94352fcdb749db6 (MIT), exercises/practice/connect; tests auto-generated from problem-specifications canonical data. Reference solution: ours, verified against the official tests below.

Tier: hard.

```python
"""Winner of the Connect game (Exercism connect)."""

from collections import deque


class ConnectGame:
    def __init__(self, board: str):
        self.grid = [line.split() for line in board.splitlines() if line.split()]

    def get_winner(self):
        grid = self.grid
        rows = len(grid)
        cols = len(grid[0]) if rows else 0

        def path_exists(player, starts, goal):
            seen = set()
            q = deque()
            for r, c in starts:
                if grid[r][c] == player:
                    seen.add((r, c))
                    q.append((r, c))
            while q:
                r, c = q.popleft()
                if goal(r, c):
                    return True
                # hex adjacency: the diagonal render (+1 indent/row) makes
                # down-left (r+1,c-1) and up-right (r-1,c+1) touch; (r+1,c+1)
                # does not (canonical tests pin this)
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, 1), (1, -1)):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols and (rr, cc) not in seen                             and grid[rr][cc] == player:
                        seen.add((rr, cc))
                        q.append((rr, cc))
            return False

        if path_exists("X", [(r, 0) for r in range(rows)], lambda r, c: c == cols - 1):
            return "X"
        if path_exists("O", [(0, c) for c in range(cols)], lambda r, c: r == rows - 1):
            return "O"
        return ""

```
