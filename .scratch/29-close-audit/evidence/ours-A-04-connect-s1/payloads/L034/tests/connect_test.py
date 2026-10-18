import unittest

from connect import ConnectGame


class TestConnectGame(unittest.TestCase):
    def test_ac1_compute_result(self):
        """AC1: Compute the result for a game of Hex / Polygon."""
        board = [
            ['.', 'O', '.', 'X', '.'],
            ['.', 'X', 'X', 'O', '.'],
            [' ', 'O', 'O', 'O', 'X', '.'],
            ['  ', '.', 'X', 'O', 'X', 'O'],
            ['   ', 'X', 'O', 'O', 'O', 'X'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertIsNone(winner)

    def test_ac2_simple_rules(self):
        """AC2: The abstract boardgame known as [Hex][hex] / Polygon / CON-TAC-TIX is quite simple."""
        board = [
            ['.', 'O', '.'],
            ['O', 'X', 'O'],
            ['.', 'O', '.'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertIsNone(winner)

    def test_ac3_parallelogram_fields(self):
        """AC3: Two players place stones on a parallelogram with hexagonal fields."""
        board = [
            ['O', '.', 'X'],
            ['X', 'O', '.'],
            ['.', 'X', 'O'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertIsNone(winner)

    def test_ac4_opposite_side_connection(self):
        """AC4: The player to connect his/her stones to the opposite side first wins."""
        board = [
            ['O', '.', '.'],
            ['O', 'X', '.'],
            ['.', 'O', '.'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertEqual(winner, 'O')

    def test_ac5_side_assignment(self):
        """AC5: The four sides of the parallelogram are divided between the two players."""
        board = [
            ['X', '.', '.'],
            ['X', 'O', '.'],
            ['.', 'X', 'O'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertEqual(winner, 'X')

    def test_ac6_compute_winner(self):
        """AC6: Your goal is to build a program that given a simple representation of a board computes the winner."""
        board = [
            ['O', '.', 'X'],
            ['O', 'X', '.'],
            ['.', 'O', 'X'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertIsNone(winner)

    def test_ac7_unfair_games(self):
        """AC7: Note that all games need not be "fair" (mismatched piece counts)."""
        board = [
            ['O', '.', '.'],
            ['.', 'X', '.'],
            ['.', '.', 'O'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertIsNone(winner)

    def test_ac8_board_looks(self):
        """AC8: The boards look like the provided example."""
        board = [
            ['.', 'O', '.', 'X', '.'],
            ['.', 'X', 'X', 'O', '.'],
            [' ', 'O', 'O', 'O', 'X', '.'],
            ['  ', '.', 'X', 'O', 'X', 'O'],
            ['   ', 'X', 'O', 'O', 'O', 'X'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertIsNone(winner)

    def test_ac9_player_directions(self):
        """AC9: "Player O" plays from top to bottom, "Player X" from left to right."""
        board = [
            ['O', '.', '.'],
            ['O', 'X', '.'],
            ['.', 'O', '.'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertEqual(winner, 'O')

    def test_ac10_example_no_winner(self):
        """AC10: In the example, O connects left to right but nobody has won since O didn't connect top and bottom."""
        board = [
            ['.', 'O', '.', 'X', '.'],
            ['.', 'X', 'X', 'O', '.'],
            [' ', 'O', 'O', 'O', 'X', '.'],
            ['  ', '.', 'X', 'O', 'X', 'O'],
            ['   ', 'X', 'O', 'O', 'O', 'X'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertIsNone(winner)

    def test_ac11_hex_reference(self):
        """AC11: [hex]: https://en.wikipedia.org/wiki/Hex_%28board_game%29"""
        board = [
            ['O', '.', 'X'],
            ['X', 'O', '.'],
            ['.', 'X', 'O'],
        ]
        game = ConnectGame(board)
        winner = game.get_winner()
        self.assertIsNone(winner)


if __name__ == '__main__':
    unittest.main()
