def proteins(strand):
    protein = []
    for i in range(0, len(strand), 3):
        codon = strand[i:i+3]
        if codon in ['UAA', 'UAG', 'UGA']:
            break
        elif codon == 'AUG':
            protein.append('Methionine')
        elif codon in ['UUU', 'UUC']:
            protein.append('Phenylalanine')
        elif codon in ['UUA', 'UUG']:
            protein.append('Leucine')
        elif codon in ['UCU', 'UCC', 'UCA', 'UCG']:
            protein.append('Serine')
        elif codon in ['UAU', 'UAC']:
            protein.append('Tyrosine')
        elif codon in ['UGU', 'UGC']:
            protein.append('Cysteine')
        elif codon == 'UGG':
            protein.append('Tryptophan')
    return protein
