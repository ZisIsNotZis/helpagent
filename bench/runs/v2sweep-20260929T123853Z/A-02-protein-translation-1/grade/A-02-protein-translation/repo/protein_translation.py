def proteins(strand):
    codons = [strand[i:i+3] for i in range(0, len(strand), 3)]
    proteins = []
    for codon in codons:
        if codon in ['UAA', 'UAG', 'UGA']:
            break
        if codon == 'AUG':
            proteins.append('Methionine')
        elif codon in ['UUU', 'UUC']:
            proteins.append('Phenylalanine')
        elif codon in ['UUA', 'UUG']:
            proteins.append('Leucine')
        elif codon in ['UCU', 'UCC', 'UCA', 'UCG']:
            proteins.append('Serine')
        elif codon in ['UAU', 'UAC']:
            proteins.append('Tyrosine')
        elif codon in ['UGU', 'UGC']:
            proteins.append('Cysteine')
        elif codon == 'UGG':
            proteins.append('Tryptophan')
    return proteins
