def proteins(strand):
    protein = []
    codon = 0
    while codon < len(strand) - 2:
        codon_sequence = strand[codon:codon + 3]
        if codon_sequence in ['UAA', 'UAG', 'UGA']:
            break
        protein.append(codon_to_amino_acid(codon_sequence))
        codon += 3
    return protein


def codon_to_amino_acid(codon):
    codon_map = {
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
        'UGG': 'Tryptophan',
    }
    return codon_map.get(codon, '')
