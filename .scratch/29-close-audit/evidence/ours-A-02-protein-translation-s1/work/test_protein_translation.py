import unittest

from protein_translation import proteins


class TestProteinTranslation(unittest.TestCase):
    def test_auguuuucu(self):
        self.assertEqual(proteins("AUGUUUUCU"), "Methionine-Phenylalanine-Serine")

    def test_stop_codon(self):
        self.assertEqual(proteins("AUGUUUUCUUAAAUG"), "Methionine-Phenylalanine-Serine")

    def test_empty_sequence(self):
        self.assertEqual(proteins(""), "")


if __name__ == "__main__":
    unittest.main()
