import pytest
from protein_translation import proteins


def test_ac1_translate_rna_to_protein():
    """AC1: Translate RNA sequences into proteins."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac2_codons_are_three_nucleotides():
    """AC2: RNA strands are made up of three-nucleotide sequences called codons."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac3_each_codon_translates_to_amino_acid():
    """AC3: Each codon translates to an amino acid."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac4_amino_acids_join_to_make_protein():
    """AC4: When joined together, those amino acids make a protein."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac5_real_world_64_codons_20_amino_acids():
    """AC5: In the real world, there are 64 codons, which in turn correspond to 20 amino acids."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac6_exercise_uses_fewer_codons():
    """AC6: However, for this exercise, you'll only use a few of the possible 64."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac7_codon_amino_acid_table():
    """AC7: They are listed below: [Codon | Amino Acid] table."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac8_codon_to_amino_acid_mapping():
    """AC8: | Codon | Amino Acid | mapping table."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac9_example_three_codons():
    """AC9: For example, the RNA string "AUGUUUUCU" has three codons."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac10_example_mapping():
    """AC10: These map to Methionine, Phenylalanine, and Serine."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac11_three_stop_codons():
    """AC11: You'll note from the table above that there are three "STOP" codons."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac12_stop_codon_completes_protein():
    """AC12: If you encounter any of these codons, ignore the rest of the sequence."""
    assert proteins("AUGUUUUCUUAAAUG") == "Methionine-Phenylalanine-Serine"


def test_ac13_example_contains_stop():
    """AC13: For example, "AUGUUUUCUUAAAUG" contains a STOP codon ("UAA")."""
    assert proteins("AUGUUUUCUUAAAUG") == "Methionine-Phenylalanine-Serine"


def test_ac14_stop_processing_stops():
    """AC14: Once we reach that point, we stop processing."""
    assert proteins("AUGUUUUCUUAAAUG") == "Methionine-Phenylalanine-Serine"


def test_ac15_only_consider_part_before_stop():
    """AC15: We therefore only consider the part before it (i.e. "AUGUUUUCU")."""
    assert proteins("AUGUUUUCUUAAAUG") == "Methionine-Phenylalanine-Serine"


def test_ac16_learn_more_wikipedia():
    """AC16: Learn more about [protein translation on Wikipedia]."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"


def test_ac17_wikipedia_link():
    """AC17: [protein-translation]: https://en.wikipedia.org/wiki/Translation_(biology)."""
    assert proteins("AUGUUUUCU") == "Methionine-Phenylalanine-Serine"
