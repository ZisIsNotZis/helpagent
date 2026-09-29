def proteins(strand):
    result = []
    i = 0
    while i < len(strand) - 2:
        codon = strand[i:i+3]
        if codon in ["UAA", "UAG", "UGA"]:
            break
        if codon == "AUG":
            result.append("Methionine")
        elif codon in ["UUU", "UUC"]:
            result.append("Phenylalanine")
        elif codon in ["UUA", "UUG"]:
            result.append("Leucine")
        elif codon in ["UCU", "UCC", "UCA", "UCG"]:
            result.append("Serine")
        elif codon in ["UAU", "UAC"]:
            result.append("Tyrosine")
        elif codon in ["UGU", "UGC"]:
            result.append("Cysteine")
        elif codon == "UGG":
            result.append("Tryptophan")
        i += 3
    return result
