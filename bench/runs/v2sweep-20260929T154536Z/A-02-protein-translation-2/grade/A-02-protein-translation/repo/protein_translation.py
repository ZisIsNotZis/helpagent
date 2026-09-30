def proteins(strand):
    protein = []
    for i in range(0, len(strand), 3):
        codon = strand[i:i+3]
        if codon in ['UAA', 'UAG', 'UGA']:
            break
        if codon == 'AUG':
            protein.append('M')
        elif codon in ['UUU', 'UUC']:
            protein.append('F')
        elif codon in ['UUA', 'UUG']:
            protein.append('L')
        elif codon in ['UCU', 'UCC', 'UCA', 'UCG']:
            protein.append('S')
        elif codon in ['UAU', 'UAC']:
            protein.append('Y')
        elif codon in ['UGU', 'UGC']:
            protein.append('C')
        elif codon == 'UGG':
            protein.append('W')
    return ''.join(protein)