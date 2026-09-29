def proteins(strand):
    result = []
    i = 0
    while i < len(strand):
        codon = strand[i:i+3]
        if codon in ('UAA', 'UAG', 'UGA'):
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
        }.get(codon)
        if amino_acid:
            result.append(amino_acid)
        i += 3
    return result
