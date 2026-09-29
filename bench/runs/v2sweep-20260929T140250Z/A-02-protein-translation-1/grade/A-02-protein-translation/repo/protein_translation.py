def proteins(strand):
    codon_table = {
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

    proteins_list = []
    i = 0

    while i < len(strand) - 2:
        codon = strand[i:i + 3]
        if codon in codon_table:
            if codon == "STOP":
                break
            proteins_list.append(codon_table[codon])
        i += 3

    return proteins_list
