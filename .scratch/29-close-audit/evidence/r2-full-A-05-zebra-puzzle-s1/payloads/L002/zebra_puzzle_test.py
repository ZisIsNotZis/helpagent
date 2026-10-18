import unittest

from zebra_puzzle import drinks_water, owns_zebra


class TestZebraPuzzle(unittest.TestCase):
    def test_drinks_water(self):
        self.assertEqual(drinks_water(), "water")

    def test_owns_zebra(self):
        self.assertEqual(owns_zebra(), "Japanese")


if __name__ == "__main__":
    unittest.main()
