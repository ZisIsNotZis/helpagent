import unittest

from book_store import total


def test_basket_two_different_books():
    """Pins the desired end state: 2 different books yield a 5% discount.
    """
    basket = [1, 2]
    expected = 2 * 8 * 0.95
    assert total(basket) == expected


def test_basket_three_different_books():
    """Pins the desired end state: 3 different books yield a 10% discount.
    """
    basket = [1, 2, 3]
    expected = 3 * 8 * 0.9
    assert total(basket) == expected


def test_basket_four_different_books():
    """Pins the desired end state: 4 different books yield a 20% discount.
    """
    basket = [1, 2, 3, 4]
    expected = 4 * 8 * 0.8
    assert total(basket) == expected


def test_basket_all_five_books():
    """Pins the desired end state: all 5 books yield a 25% discount.
    """
    basket = [1, 2, 3, 4, 5]
    expected = 5 * 8 * 0.75
    assert total(basket) == expected


if __name__ == '__main__':
    unittest.main()
