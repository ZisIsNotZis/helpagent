import pytest

from book_store import total


def test_ac1_basket_discounts():
    """AC1: Code calculates price of any conceivable basket giving max discount."""
    basket = [1, 2, 3, 4, 5]
    assert total(basket) == 5 * 8 * (1 - 0.25)


def test_ac2_single_book_cost():
    """AC2: One copy of any book costs $8."""
    assert total([1]) == 8.0


def test_ac3_two_different_books_5pct():
    """AC3: Two different books get a 5% discount."""
    assert total([1, 2]) == 2 * 8 * (1 - 0.05)


def test_ac4_three_different_books_10pct():
    """AC4: Three different books get a 10% discount."""
    assert total([1, 2, 3]) == 3 * 8 * (1 - 0.10)


def test_ac5_four_different_books_20pct():
    """AC5: Four different books get a 20% discount."""
    assert total([1, 2, 3, 4]) == 4 * 8 * (1 - 0.20)


def test_ac6_all_five_books_25pct():
    """AC6: All five books get a 25% discount."""
    assert total([1, 2, 3, 4, 5]) == 5 * 8 * (1 - 0.25)


def test_ac7_three_different_fourth_no_discount():
    """AC7: Four books with 3 different titles get 10% on 3, 4th costs $8."""
    basket = [1, 2, 3, 1]
    expected = 3 * 8 * (1 - 0.10) + 1 * 8 * (1 - 0.0)
    assert total(basket) == expected


def test_ac8_max_discount_basket():
    """AC8: Mission is to calculate price giving as big a discount as possible."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac9_example_basket():
    """AC9: Example basket calculation is correctly executed."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    assert total(basket) == 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)


def test_ac10_two_first_books():
    """AC10: Basket includes 2 copies of the first book."""
    basket = [1, 1, 2, 3, 4, 5]
    assert total(basket) == 2 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)


def test_ac11_two_second_books():
    """AC11: Basket includes 2 copies of the second book."""
    basket = [1, 2, 2, 3, 4, 5]
    assert total(basket) == 2 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)


def test_ac12_two_third_books():
    """AC12: Basket includes 2 copies of the third book."""
    basket = [1, 2, 3, 3, 4, 5]
    assert total(basket) == 2 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)


def test_ac13_one_fourth_book():
    """AC13: Basket includes 1 copy of the fourth book."""
    basket = [1, 2, 3, 4, 5]
    assert total(basket) == 5 * 8 * (1 - 0.25)


def test_ac14_one_fifth_book():
    """AC14: Basket includes 1 copy of the fifth book."""
    basket = [1, 2, 3, 4, 5]
    assert total(basket) == 5 * 8 * (1 - 0.25)


def test_ac15_grouping_way_one():
    """AC15: One way of grouping the 8 books is valid."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac16_group_of_five():
    """AC16: Includes a group of 5 (1st, 2nd, 3rd, 4th, 5th)."""
    basket = [1, 2, 3, 4, 5]
    assert total(basket) == 5 * 8 * (1 - 0.25)


def test_ac17_group_of_three():
    """AC17: Includes a group of 3 (1st, 2nd, 3rd)."""
    basket = [1, 2, 3]
    assert total(basket) == 3 * 8 * (1 - 0.10)


def test_ac18_total_given():
    """AC18: Total for the first grouping is correctly calculated."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac19_five_books_discount():
    """AC19: 5 books at a 25% discount."""
    assert total([1, 2, 3, 4, 5]) == 5 * 8 * (1 - 0.25)


def test_ac20_three_books_discount():
    """AC20: 3 books at a 10% discount."""
    assert total([1, 2, 3]) == 3 * 8 * (1 - 0.10)


def test_ac21_resulting_total():
    """AC21: Resulting total for first grouping is correct."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac22_five_discount_calc():
    """AC22: 5 books at 25% discount calculation."""
    assert total([1, 2, 3, 4, 5]) == 5 * 8 * (1 - 0.25)


def test_ac23_three_discount_calc():
    """AC23: 3 books at 10% discount calculation."""
    assert total([1, 2, 3]) == 3 * 8 * (1 - 0.10)


def test_ac24_total_51_60():
    """AC24: Total equals $51.60 for the first grouping."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    assert total(basket) == 51.60


def test_ac25_different_grouping():
    """AC25: A different way of grouping the 8 books is valid."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    expected = 4 * 8 * (1 - 0.20) + 4 * 8 * (1 - 0.20)
    assert total(basket) == expected


def test_ac26_group_of_four():
    """AC26: Includes a group of 4 books (1st, 2nd, 3rd, 4th)."""
    basket = [1, 2, 3, 4]
    assert total(basket) == 4 * 8 * (1 - 0.20)


def test_ac27_group_of_four_alt():
    """AC27: Includes a group of 4 books (1st, 2nd, 3rd, 5th)."""
    basket = [1, 2, 3, 5]
    assert total(basket) == 4 * 8 * (1 - 0.20)


def test_ac28_four_books_discount():
    """AC28: 4 books at a 20% discount."""
    assert total([1, 2, 3, 4]) == 4 * 8 * (1 - 0.20)


def test_ac29_first_four_calc():
    """AC29: First group of 4 books calculation."""
    assert total([1, 2, 3, 4]) == 4 * 8 * (1 - 0.20)


def test_ac30_second_four_calc():
    """AC30: Second group of 4 books calculation."""
    assert total([1, 2, 3, 5]) == 4 * 8 * (1 - 0.20)


def test_ac31_total_51_20():
    """AC31: Total equals $51.20 for the second grouping."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    assert total(basket) == 51.20


def test_ac32_max_discount_final():
    """AC32: $51.20 is the price with the biggest discount."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    assert total(basket) == 51.20
