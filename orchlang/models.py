"""Model profiles: chat templates, tokenizers and stop tokens.

A profile renders the raw prompt and counts complete requests with the model's
own tokenizer. Compiler sizing targets remain heuristics; runtime admission and
padding count the completed request exactly in that model contract's unit.
"""
from __future__ import annotations

import json
import os
import ctypes
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

PLACEHOLDER = "\x00{}\x00"
_backend_handles = []
_backends_loaded = False


def initialize_backends():
    """Optional explicitly pinned ggml backend directory for local GPU serving.

    LLAMA_CPP_LIB_PATH must be set before importing llama_cpp. The execution
    manifest records all backend library hashes; default wheel use is unchanged.
    """
    global _backends_loaded
    directory = os.environ.get("ORCHLANG_GGML_BACKENDS")
    if not directory or _backends_loaded:
        return
    from pathlib import Path
    base = Path(directory).resolve()
    if not base.is_dir():
        raise ValueError("declared backend directory is absent")
    if os.name == "nt":
        _backend_handles.append(os.add_dll_directory(str(base)))
    library = base / ("ggml.dll" if os.name == "nt" else "libggml.so")
    handle = ctypes.CDLL(str(library))
    handle.ggml_backend_load_all_from_path.argtypes = [ctypes.c_char_p]
    handle.ggml_backend_load_all_from_path(str(base).encode("utf-8"))
    _backend_handles.append(handle)
    _backends_loaded = True


@dataclass
class Template:
    family: str
    default_system: Optional[str]
    turn: str          # format with role, content
    generation: str    # assistant header appended at the end
    pad_open: str      # wrapper for the padding message
    pad_close: str

    def render(self, messages: List[Tuple[str, str]]) -> str:
        if self.family == "llama3":
            return self._render_llama3(messages)
        out = []
        if self.default_system is not None and (not messages or messages[0][0] != "system"):
            out.append(self.turn.format(role="system", content=self.default_system))
        for role, content in messages:
            out.append(self.turn.format(role=role, content=content))
        out.append(self.generation)
        return "".join(out)


    def _render_llama3(self, messages: List[Tuple[str, str]]) -> str:
        """Llama 3.2 Instruct GGUF template (no tools): BOS, a system turn holding
        the knowledge-date preamble and the trimmed system message, trimmed turns.
        The date is the template's own fallback, so rendering is deterministic."""
        system = ""
        if messages and messages[0][0] == "system":
            system, messages = messages[0][1].strip(), messages[1:]
        out = ["<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
               "Cutting Knowledge Date: December 2023\nToday Date: 26 Jul 2024\n\n" + system + "<|eot_id|>"]
        for role, content in messages:
            out.append(self.turn.format(role=role, content=content.strip()))
        out.append(self.generation)
        return "".join(out)


TEMPLATES: Dict[str, Template] = {
    "qwen2": Template(
        family="qwen2",
        default_system="You are Qwen, created by Alibaba Cloud. You are a helpful assistant.",
        turn="<|im_start|>{role}\n{content}<|im_end|>\n",
        generation="<|im_start|>assistant\n",
        pad_open="<|im_start|>system\n",
        pad_close="<|im_end|>\n",
    ),
    "llama3": Template(
        family="llama3",
        default_system=None,
        turn="<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>",
        generation="<|start_header_id|>assistant<|end_header_id|>\n\n",
        pad_open="<|start_header_id|>system<|end_header_id|>\n\n",
        pad_close="<|eot_id|>",
    ),
}


def token_piece_bytes(model, token: int, special: bool = False) -> bytes:
    """Read a complete native token piece, including pieces longer than 32 bytes.

    The pinned Python wrapper's fixed-buffer detokenizer can drop a piece when
    the native API returns a negative required buffer length. Cache only complete
    successful reads, and preserve the wrapper's special-token convention.
    """
    from llama_cpp import llama_token_to_piece
    cache = getattr(model, "_orchlang_piece_cache", None)
    if cache is None:
        cache = model._orchlang_piece_cache = {}
    key = (int(token), special)
    if key not in cache:
        buffer = ctypes.create_string_buffer(32)
        count = llama_token_to_piece(model._model.vocab, int(token), buffer, len(buffer), 0, special)
        if count < 0:
            buffer = ctypes.create_string_buffer(-count)
            count = llama_token_to_piece(model._model.vocab, int(token), buffer, len(buffer), 0, special)
        if not 0 <= count <= len(buffer):
            raise ValueError("native token piece exceeds the declared buffer")
        cache[key] = bytes(buffer.raw[:count])
    return cache[key]


def detokenize_bytes(model, ids) -> bytes:
    output = b"".join(token_piece_bytes(model, token) for token in ids)
    if ids and ids[0] == model.token_bos() and output.startswith(b" "):
        output = output[1:]
    return output


@dataclass
class Profile:
    key: str
    gguf: str
    template: str
    filler: str = " ."
    pad_mode: str = "isolated"   # "isolated" (serving-side) or "inband" (filler turn in the prompt)
    pad_position: str = "end"    # in-band only: "end" or "after_first"
    stop: List[str] = field(default_factory=list)
    bos: str = ""
    sha256: Optional[str] = None
    decoding_grammar: Optional[str] = None

    @property
    def tmpl(self) -> Template:
        return TEMPLATES[self.template]


class Tokenizer:
    """Exact tokenizer of a GGUF model (vocabulary only, no weights)."""

    def __init__(self, gguf: str):
        from llama_cpp import Llama
        initialize_backends()
        self._m = Llama(model_path=gguf, vocab_only=True, verbose=False)

    def encode(self, text: str) -> List[int]:
        return self._m.tokenize(text.encode("utf-8"), add_bos=False, special=True)

    def encode_plain(self, text: str) -> List[int]:
        return self._m.tokenize(text.encode("utf-8"), add_bos=False, special=False)

    def decode(self, ids: List[int]) -> str:
        return detokenize_bytes(self._m, ids).decode("utf-8", errors="ignore")

    def count(self, text: str) -> int:
        return len(self.encode(text))


class CharTokenizer:
    """Deterministic test tokenizer: one token per character."""

    def encode(self, text: str) -> List[int]:
        return [ord(c) for c in text]

    encode_plain = encode

    def decode(self, ids: List[int]) -> str:
        return "".join(chr(i) for i in ids)

    def count(self, text: str) -> int:
        return len(text)


def load_profiles(path: Optional[str] = None) -> Dict[str, Profile]:
    path = path or os.environ.get("ORCHLANG_MODELS", "models.json")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    out = {}
    for key, cfg in raw.items():
        gguf = cfg["gguf"]
        if not os.path.isabs(gguf):
            gguf = os.path.join(base, gguf)
        out[key] = Profile(key=key, gguf=gguf, template=cfg["template"],
                           filler=cfg.get("filler", " ."), stop=cfg.get("stop", []),
                           pad_mode=cfg.get("pad_mode", "isolated"), pad_position=cfg.get("pad_position", "end"),
                           sha256=cfg.get("sha256"), decoding_grammar=cfg.get("decoding_grammar"))
    # Resolve aliases by complete declared semantic contract, not spelling.
    # Unpinned profiles remain distinct; file hashes are checked by the custody
    # boundary before an experimental run. Different templates/stops/padding
    # policies never merge merely because the weights match.
    identities = {}
    for key in sorted(out):
        profile=out[key]
        if not profile.sha256:
            continue
        identity=(profile.sha256,profile.template,profile.filler,profile.pad_mode,
                  profile.pad_position,tuple(profile.stop),profile.bos,profile.decoding_grammar)
        owner=identities.setdefault(identity,key)
        profile.key=owner
    return out


@lru_cache(maxsize=None)
def tokenizer_for(gguf: str) -> Tokenizer:
    return Tokenizer(gguf)
