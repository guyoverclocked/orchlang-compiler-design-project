import unittest
from orchlang.runtime import LlamaBackend


class StopContract(unittest.TestCase):
    class Vocabulary:
        def token_eos(self):
            return 0

        def tokenize(self, value, **kwargs):
            return {b"EOS": [0], b"EOT": [1], b"OK": [2],
                    b"multi stop": [3, 4], b"": []}[value]

    def test_atomic_stops_are_recognized_and_deduplicated(self):
        self.assertEqual(LlamaBackend.declared_stop_ids(self.Vocabulary(), ["EOS", "EOT", "OK"]), {0, 1, 2})

    def test_multitoken_and_empty_stops_are_rejected(self):
        for stop in ("multi stop", ""):
            with self.subTest(stop=stop), self.assertRaisesRegex(ValueError, "one token ID"):
                LlamaBackend.declared_stop_ids(self.Vocabulary(), [stop])


if __name__ == "__main__":
    unittest.main()
