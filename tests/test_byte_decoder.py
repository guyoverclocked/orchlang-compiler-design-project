import ctypes
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from orchlang.models import token_piece_bytes, detokenize_bytes


class ByteDecoder(unittest.TestCase):
    class Model:
        class Native:
            vocab = None
        _model = Native()
        def token_bos(self):
            return 0

    def test_long_piece_is_resized_and_cached(self):
        piece = b" " * 128
        calls = []
        def native(vocab, token, buffer, capacity, lstrip, special):
            calls.append(capacity)
            if capacity < len(piece):
                return -len(piece)
            ctypes.memmove(buffer, piece, len(piece))
            return len(piece)
        model = self.Model()
        with patch.dict("sys.modules", {"llama_cpp": SimpleNamespace(llama_token_to_piece=native)}):
            self.assertEqual(token_piece_bytes(model, 7), piece)
            self.assertEqual(detokenize_bytes(model, [7, 7]), piece * 2)
        self.assertEqual(calls, [32, 128])

    def test_invalid_native_resize_is_rejected(self):
        with patch.dict("sys.modules", {"llama_cpp": SimpleNamespace(llama_token_to_piece=lambda *args: -128)}):
            with self.assertRaises(ValueError):
                token_piece_bytes(self.Model(), 7)

    def test_suppressed_special_piece_can_be_empty(self):
        with patch.dict("sys.modules", {"llama_cpp": SimpleNamespace(llama_token_to_piece=lambda *args: 0)}):
            self.assertEqual(detokenize_bytes(self.Model(), [2]), b"")
