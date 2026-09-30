def total(basket):
    if len(basket) == 0:
        return 0

    # Count how many copies of each book are in the basket
    counts = {}
    for book in basket:
        counts[book] = counts.get(book, 0) + 1

    # Calculate the total price without any discounts
    total_price = sum(counts[book] * 8 for book in counts)

    # Calculate the maximum possible discount by grouping books optimally
    # We want to maximize the number of books in groups of 4, 3, 2, or 1
    # but we need to consider the constraints of the discount rules.
    # The key insight is that we want to form as many groups of 4 as possible,
    # then groups of 3, then groups of 2, and finally single books.
    # However, we must be careful not to break existing groups.

    # A more robust approach is to use a greedy algorithm that prioritizes
    # larger groups first, but we need to ensure we don't overcount.
    # This is a classic problem of maximizing discount with given constraints.

    # Let's use a more direct approach based on the problem's requirements.
    # We can think of it as trying to form groups of 5, 4, 3, 2, 1
    # but with the specific discount rules.

    # A better way is to use a dynamic programming or greedy approach
    # that considers the counts of each book.

    # For this specific problem, we can use the following logic:
    # 1. First, try to form groups of 5 (25% discount)
    # 2. Then, try to form groups of 4 (20% discount)
    # 3. Then, try to form groups of 3 (10% discount)
    # 4. Then, try to form groups of 2 (5% discount)
    # 5. Finally, the remaining books are single (no discount)

    # However, the optimal grouping might not be straightforward due to the
    # constraint that groups must consist of different books (except for the
    # special case of 4 books where 3 are different and 1 is the same as one
    # of them, which still gets 10% discount on the 3 different ones).

    # Let's implement a more accurate calculation based on the problem's examples.
    # The key is to maximize the discount by optimally grouping the books.

    # We can use a greedy approach that prioritizes larger groups first.
    # We'll iterate through possible group sizes from largest to smallest.

    # First, let's calculate the total number of books
    total_books = sum(counts.values())

    # We'll use a list to keep track of how many books we have used in each group
    # and the type of group (size and discount percentage)
    groups = []

    # Start with the largest possible group size (5)
    while total_books >= 5 and len(counts) >= 5:
        # We can form a group of 5 if we have at least 5 different books
        # with at least 1 copy each
        if all(counts[book] >= 1 for book in range(1, 6)) and total_books >= 5:
            # Form a group of 5
            groups.append((5, 0.25))  # size, discount percentage
            # Reduce the count of each book by 1
            for book in range(1, 6):
                counts[book] -= 1
            total_books -= 5

    # Next, try to form groups of 4 (20% discount)
    while total_books >= 4 and len(counts) >= 4:
        # We can form a group of 4 if we have at least 4 different books
        # with at least 1 copy each
        if all(counts[book] >= 1 for book in range(1, 5)) and total_books >= 4:
            # Form a group of 4
            groups.append((4, 0.20))  # size, discount percentage
            # Reduce the count of each book by 1
            for book in range(1, 5):
                counts[book] -= 1
            total_books -= 4

    # Next, try to form groups of 3 (10% discount)
    while total_books >= 3 and len(counts) >= 3:
        # We can form a group of 3 if we have at least 3 different books
        # with at least 1 copy each
        if all(counts[book] >= 1 for book in range(1, 4)) and total_books >= 3:
            # Form a group of 3
            groups.append((3, 0.10))  # size, discount percentage
            # Reduce the count of each book by 1
            for book in range(1, 4):
                counts[book] -= 1
            total_books -= 3

    # Next, try to form groups of 2 (5% discount)
    while total_books >= 2 and len(counts) >= 2:
        # We can form a group of 2 if we have at least 2 different books
        # with at least 1 copy each
        if all(counts[book] >= 1 for book in range(1, 3)) and total_books >= 2:
            # Form a group of 2
            groups.append((2, 0.05))  # size, discount percentage
            # Reduce the count of each book by 1
            for book in range(1, 3):
                counts[book] -= 1
            total_books -= 2

    # The remaining books are single (no discount)
    remaining_books = total_books

    # Calculate the total price with discounts
    total_discounted_price = 0

    # Add the price for groups with discounts
    for group_size, discount in groups:
        # The number of books in this group is group_size
        # The discount is applied to all books in the group
        # Each book costs $8
        group_price = group_size * 8 * (1 - discount)
        total_discounted_price += group_price

    # Add the price for remaining single books (no discount)
    total_discounted_price += remaining_books * 8

    return total_discounted_price
