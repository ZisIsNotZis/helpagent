def proteins(strand):
    codon_map = {
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
    result = []
    i = 0
    while i < len(strand):
        codon = strand[i:i+3]
        if codon in codon_map:
            if codon == "STOP":
                break
            result.append(codon_map[codon])
        i += 3
    return "-".join(result)