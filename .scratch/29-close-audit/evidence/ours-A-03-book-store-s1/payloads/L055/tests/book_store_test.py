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


def test_ac6_five_different_books_25pct():
    """AC6: All five books get a 25% discount."""
    assert total([1, 2, 3, 4, 5]) == 5 * 8 * (1 - 0.25)


def test_ac7_three_distinct_four_total():
    """AC7: 4 books with 3 distinct titles get 10% on distinct, $8 on 4th."""
    basket = [1, 2, 3, 1]
    assert total(basket) == 3 * 8 * (1 - 0.10) + 1 * 8 * (1 - 0.0)


def test_ac8_max_discount_basket():
    """AC8: Mission to calculate price giving as big a discount as possible."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac9_example_basket_cost():
    """AC9: Example basket of 8 books is calculated correctly."""
    basket = [1, 1, 2, 2, 3, 3, 4, 5]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac10_two_first_books():
    """AC10: Test case includes 2 copies of the first book."""
    basket = [1, 1]
    assert total(basket) == 2 * 8 * (1 - 0.0)


def test_ac11_two_second_books():
    """AC11: Test case includes 2 copies of the second book."""
    basket = [2, 2]
    assert total(basket) == 2 * 8 * (1 - 0.0)


def test_ac12_two_third_books():
    """AC12: Test case includes 2 copies of the third book."""
    basket = [3, 3]
    assert total(basket) == 2 * 8 * (1 - 0.0)


def test_ac13_one_fourth_book():
    """AC13: Test case includes 1 copy of the fourth book."""
    basket = [4]
    assert total(basket) == 8.0


def test_ac14_one_fifth_book():
    """AC14: Test case includes 1 copy of the fifth book."""
    basket = [5]
    assert total(basket) == 8.0


def test_ac15_grouping_way_one():
    """AC15: Test case uses one grouping of 5 and one grouping of 3."""
    basket = [1, 2, 3, 4, 5, 1, 2, 3]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac16_group_of_five():
    """AC16: Test case includes 1 group of 5 (1st, 2nd, 3rd, 4th, 5th)."""
    basket = [1, 2, 3, 4, 5]
    assert total(basket) == 5 * 8 * (1 - 0.25)


def test_ac17_group_of_three():
    """AC17: Test case includes 1 group of 3 (1st, 2nd, 3rd)."""
    basket = [1, 2, 3]
    assert total(basket) == 3 * 8 * (1 - 0.10)


def test_ac18_total_given():
    """AC18: Test case verifies the stated total calculation for the first grouping."""
    basket = [1, 2, 3, 4, 5, 1, 2, 3]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac19_five_books_discount():
    """AC19: Test case asserts 5 books at a 25% discount."""
    basket = [1, 2, 3, 4, 5]
    assert total(basket) == 5 * 8 * (1 - 0.25)


def test_ac20_three_books_discount():
    """AC20: Test case asserts 3 books at a 10% discount."""
    basket = [1, 2, 3]
    assert total(basket) == 3 * 8 * (1 - 0.10)


def test_ac21_resulting_total():
    """AC21: Test case asserts the resulting total for the first grouping."""
    basket = [1, 2, 3, 4, 5, 1, 2, 3]
    expected = 5 * 8 * (1 - 0.25) + 3 * 8 * (1 - 0.10)
    assert total(basket) == expected


def test_ac22_five_book_component():
    """AC22: Test case verifies the 5 books at 25% discount component."""
    basket = [1, 2, 3, 4, 5]
    assert total(basket) == 5 * 8 * (1 - 0.25)


def test_ac23_three_book_component():
    """AC23: Test case verifies the 3 books at 10% discount component."""
    basket = [1, 2, 3]
    assert total(basket) == 3 * 8 * (1 - 0.10)


def test_ac24_total_51_60():
    """AC24: Test case asserts the total equals $51.60 for the first grouping."""
    basket = [1, 2, 3, 4, 5, 1, 2, 3]
    assert total(basket) == 51.60


def test_ac25_different_grouping():
    """AC25: Test case uses a different grouping of 4 and 4 books."""
    basket = [1, 2, 3, 4, 1, 2, 3, 5]
    expected = 4 * 8 * (1 - 0.20) + 4 * 8 * (1 - 0.20)
    assert total(basket) == expected


def test_ac26_group_of_four():
    """AC26: Test case includes 1 group of 4 books (1st, 2nd, 3rd, 4th)."""
    basket = [1, 2, 3, 4]
    assert total(basket) == 4 * 8 * (1 - 0.20)


def test_ac27_group_of_four_two():
    """AC27: Test case includes 1 group of 4 books (1st, 2nd, 3rd, 5th)."""
    basket = [1, 2, 3, 5]
    assert total(basket) == 4 * 8 * (1 - 0.20)


def test_ac28_four_books_discount():
    """AC28: Test case asserts 4 books at a 20% discount."""
    basket = [1, 2, 3, 4]
    assert total(basket) == 4 * 8 * (1 - 0.20)


def test_ac29_first_component():
    """AC29: Test case verifies the first 4 books at 20% discount component."""
    basket = [1, 2, 3, 4]
    assert total(basket) == 4 * 8 * (1 - 0.20)


def test_ac30_second_component():
    """AC30: Test case verifies the second 4 books at 20% discount component."""
    basket = [1, 2, 3, 5]
    assert total(basket) == 4 * 8 * (1 - 0.20)


def test_ac31_total_51_20():
    """AC31: Test case asserts the total equals $51.20 for the second grouping."""
    basket = [1, 2, 3, 4, 1, 2, 3, 5]
    expected = 4 * 8 * (1 - 0.20) + 4 * 8 * (1 - 0.20)
    assert total(basket) == expected


def test_ac32_max_discount_51_20():
    """AC32: Test case asserts $51.20 is the price with the biggest discount."""
    basket = [1, 2, 3, 4, 1, 2, 3, 5]
    expected = 4 * 8 * (1 - 0.20) + 4 * 8 * (1 - 0.20)
    assert total(basket) == expected
