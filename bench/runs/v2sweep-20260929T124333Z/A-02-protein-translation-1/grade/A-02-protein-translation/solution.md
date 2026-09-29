# A-02-protein-translation - reference solution (never shown to a run)

Provenance: tests + instructions from exercism/python@1f6aab8667bf653b10cc3799f94352fcdb749db6 (MIT), exercises/practice/protein-translation; tests auto-generated from problem-specifications canonical data. Reference solution: ours, verified against the official tests below.

Tier: medium.

```python
"""Translate RNA strands into proteins (Exercism protein-translation)."""

CODONS = {
    "AUG": "Methionine", "UUU": "Phenylalanine", "UUC": "Phenylalanine",
    "UUA": "Leucine", "UUG": "Leucine", "UCU": "Serine", "UCC": "Serine",
    "UCA": "Serine", "UCG": "Serine", "UAU": "Tyrosine", "UAC": "Tyrosine",
    "UGU": "Cysteine", "UGC": "Cysteine", "UGG": "Tryptophan",
}
STOPS = {"UAA", "UAG", "UGA"}


def proteins(strand: str) -> list:
    out = []
    for i in range(0, len(strand), 3):
        codon = strand[i:i + 3]
        if codon in STOPS:
            break
        if codon not in CODONS:
            raise ValueError(f"invalid codon: {codon!r}")
        out.append(CODONS[codon])
    return out

```
