def proteins(strand):
    result = []
    i = 0
    codons = [strand[i:i+3] for i in range(0, len(strand), 3)]
    for codon in codons:
        if codon in ['UAA', 'UAG', 'UGA']:
            break
        amino_acid = {
            'AUG': 'Methionine',
            'UUU': 'Phenylalanine',
            'UUC': 'Phenylalanine',
            'UUA': 'Leucine',
            'UUG': 'Leucine',
            'UCU': 'Serine',
            'UCC': 'Serine',
            'UCA': 'Serine',
            'UCG': 'Serine',
            'UAU': 'Tyrosine',
            'UAC': 'Tyrosine',
            'UGU': 'Cysteine',
            'UGC': 'Cysteine',
            'UGG': 'Tryptophan'
        }[codon]
        result.append(amino_acid)
    return '-'.join(result)