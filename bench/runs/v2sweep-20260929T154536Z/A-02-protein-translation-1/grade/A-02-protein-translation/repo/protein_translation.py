def proteins(strand):
    codon_to_aa = {
        "AUG": "Methionine",
        "UUU": "Phenylalanine",
        "UUC": "Phenylalanine",
        "UUA": "Leucine",
        "UUG": "Leucine",
        "UCU": "Serine",
        "UCC": "Serine",
        "UCA": "Serine",
        "UCG": "Serine",
        "UAU": "Tyrosine",
        "UAC": "Tyrosine",
        "UGU": "Cysteine",
        "UGC": "Cysteine",
        "UGG": "Tryptophan",
        "UAA": "STOP",
        "UAG": "STOP",
        "UGA": "STOP",
    }
    protein = ""
    i = 0
    while i < len(strand) - 2:
        codon = strand[i:i + 3]
        if codon in codon_to_aa:
            aa = codon_to_aa[codon]
            if aa == "STOP":
                break
            protein += aa
        i += 3
    return protein
