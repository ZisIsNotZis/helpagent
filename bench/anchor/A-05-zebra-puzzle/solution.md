# A-05-zebra-puzzle - reference solution (never shown to a run)

Provenance: tests + instructions from exercism/python@1f6aab8667bf653b10cc3799f94352fcdb749db6 (MIT), exercises/practice/zebra-puzzle; tests auto-generated from problem-specifications canonical data. Reference solution: ours, verified against the official tests below.

Tier: very-hard.

```python
"""Solve the zebra puzzle (Exercism zebra-puzzle)."""

from itertools import permutations

NATIONS = ["Englishman", "Spaniard", "Ukrainian", "Norwegian", "Japanese"]
COLORS = ["red", "green", "ivory", "yellow", "blue"]
PETS = ["dog", "snails", "fox", "horse", "zebra"]
DRINKS = ["coffee", "tea", "milk", "orange_juice", "water"]
SMOKES = ["old_gold", "kools", "chesterfields", "lucky_strike", "parliaments"]

_RESULT = None


def _solve():
    # Constraints (canonical 15): norwegian=house1, milk=house3, green right of
    # ivory, englishman=red, spaniard=dog+coffee, ukrainian=tea, old_gold=snails,
    # kools=yellow, chesterfields next to fox, kools next to horse,
    # lucky_strike=orange_juice, japanese=parliaments, norwegian next to blue.
    for nations in permutations(NATIONS):
        if nations[0] != "Norwegian":
            continue
        for colors in permutations(COLORS):
            if colors.index("red") != nations.index("Englishman"):
                continue
            if colors.index("green") != colors.index("ivory") + 1:
                continue
            if abs(colors.index("blue") - 0) != 1:
                continue
            for drinks in permutations(DRINKS):
                if drinks[2] != "milk":
                    continue
                if drinks[colors.index("green")] != "coffee":
                    continue
                if drinks[nations.index("Ukrainian")] != "tea":
                    continue
                for smokes in permutations(SMOKES):
                    if smokes[colors.index("yellow")] != "kools":
                        continue
                    if smokes[nations.index("Japanese")] != "parliaments":
                        continue
                    if drinks[smokes.index("lucky_strike")] != "orange_juice":
                        continue
                    for pets in permutations(PETS):
                        if pets[nations.index("Spaniard")] != "dog":
                            continue
                        if pets[smokes.index("old_gold")] != "snails":
                            continue
                        ki = smokes.index("kools")
                        if abs(ki - pets.index("horse")) != 1:
                            continue
                        ci = smokes.index("chesterfields")
                        if abs(ci - pets.index("fox")) != 1:
                            continue
                        return (nations[drinks.index("water")],
                                nations[pets.index("zebra")])
    raise AssertionError("no solution")


def drinks_water():
    global _RESULT
    if _RESULT is None:
        _RESULT = _solve()
    return _RESULT[0]


def owns_zebra():
    global _RESULT
    if _RESULT is None:
        _RESULT = _solve()
    return _RESULT[1]

```
