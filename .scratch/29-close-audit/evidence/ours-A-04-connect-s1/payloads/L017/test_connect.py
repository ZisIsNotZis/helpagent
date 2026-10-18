import unittest

from connect import ConnectGame


class TestConnectGame(unittest.TestCase):
    def test_determine_winner(self):
        # Board where O connects top to bottom.
        board = [
            ['.', 'O', '.', 'X', '.'],
            ['.', 'X', 'X', 'O', '.'],
            [' ', 'O', 'O', 'O', 'X'],
            ['  ', '.', 'X', 'O', 'X'],
            ['   ', 'X', 'O', 'O', 'O', 'X'],
        ]
        game = ConnectGame(board)
        self.assertEqual(game.get_winner(), 'O')

    def test_determine_winner_no_winner(self):
        # Board where no player has connected across.
        board = [
            ['.', 'O', '.', 'X', '.'],
            ['.', 'X', 'X', 'O', '.'],
            [' ', 'O', 'O', 'O', 'X'],
            ['  ', '.', 'X', 'O', 'X'],
            ['   ', 'X', 'O', 'O', 'O', 'X'],
        ]
        game = ConnectGame(board)
        self.assertIsNone(game.get_winner())


if __name__ == '__main__':
    unittest.main()
