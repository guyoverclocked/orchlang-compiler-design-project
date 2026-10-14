"""Bounded strict JSON parsing for capsule artifacts and child protocol data."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any


MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_JSON_ITEMS = 500_000
MAX_JSON_DEPTH = 128
MAX_STRING_BYTES = 2 * 1024 * 1024
MAX_INTEGER_DIGITS = 128
MAX_INTEGER_BITS = 512
_INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]+\Z")


class StrictJSONError(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(f"duplicate JSON object key: {key[:80]!r}")
        result[key] = value
    return result


def _parse_integer(text: str) -> int:
    if not _INTEGER.fullmatch(text):
        raise StrictJSONError("noncanonical JSON integer")
    digits = text[1:] if text.startswith("-") else text
    if len(digits) > MAX_INTEGER_DIGITS:
        raise StrictJSONError(f"JSON integer exceeds {MAX_INTEGER_DIGITS} digits")
    value = int(text)
    if value.bit_length() > MAX_INTEGER_BITS:
        raise StrictJSONError(f"JSON integer exceeds {MAX_INTEGER_BITS} bits")
    return value


def _parse_float(text: str) -> float:
    # Existing Document trace values use ordinary decimals (for example 0.875).
    # Exponent notation is unnecessary in this wire format and is rejected.
    if len(text) > 128 or not _DECIMAL.fullmatch(text):
        raise StrictJSONError("JSON float must be a bounded plain decimal without an exponent")
    value = float(text)
    if not math.isfinite(value):
        raise StrictJSONError("non-finite JSON float")
    # Keep canonical serialization in plain-decimal form as well.
    rendered = json.dumps(value, allow_nan=False)
    if "e" in rendered.lower():
        raise StrictJSONError("JSON float is outside the plain-decimal serialization range")
    if rendered != text:
        raise StrictJSONError("JSON float is not in canonical shortest-decimal form")
    if value == 0.0 and text.startswith("-"):
        raise StrictJSONError("negative zero is not a supported JSON number")
    return value


def _reject_constant(text: str) -> Any:
    raise StrictJSONError(f"non-finite JSON value is unsupported: {text}")


def validate_tree(value: Any, *, where: str = "JSON value") -> None:
    pending: list[tuple[Any, int, bool]] = [(value, 1, False)]
    active: set[int] = set()
    item_count = 0
    estimated_bytes = 0

    def account(amount: int) -> None:
        nonlocal estimated_bytes
        estimated_bytes += amount
        if estimated_bytes > MAX_JSON_BYTES:
            raise StrictJSONError(f"{where} exceeds the decoded data limit")

    while pending:
        item, depth, exiting = pending.pop()
        if exiting:
            active.remove(id(item))
            continue
        item_count += 1
        if item_count > MAX_JSON_ITEMS:
            raise StrictJSONError(f"{where} exceeds {MAX_JSON_ITEMS} JSON values")
        if depth > MAX_JSON_DEPTH:
            raise StrictJSONError(f"{where} exceeds JSON nesting depth {MAX_JSON_DEPTH}")
        if item is None:
            account(4)
        elif type(item) is bool:
            account(5 if item else 4)
        elif type(item) is int:
            if item.bit_length() > MAX_INTEGER_BITS:
                raise StrictJSONError(f"{where} contains an integer exceeding {MAX_INTEGER_BITS} bits")
            account(len(str(item)) + 1)
        elif type(item) is float:
            if not math.isfinite(item):
                raise StrictJSONError(f"{where} contains a non-finite float")
            rendered = json.dumps(item, allow_nan=False)
            if "e" in rendered.lower():
                raise StrictJSONError(f"{where} contains an exponent-form float")
            account(len(rendered) + 1)
        elif type(item) is str:
            try:
                encoded = item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise StrictJSONError(f"{where} contains a lone surrogate") from exc
            if len(encoded) > MAX_STRING_BYTES:
                raise StrictJSONError(f"{where} contains a string exceeding {MAX_STRING_BYTES} bytes")
            account(len(encoded) + 2 + 5 * sum(ord(char) < 0x20 for char in item))
        elif type(item) is list:
            identity = id(item)
            if identity in active:
                raise StrictJSONError(f"{where} contains a cycle")
            active.add(identity)
            account(2)
            pending.append((item, depth, True))
            pending.extend((child, depth + 1, False) for child in reversed(item))
        elif type(item) is dict:
            identity = id(item)
            if identity in active:
                raise StrictJSONError(f"{where} contains a cycle")
            active.add(identity)
            account(2)
            children = []
            for key, child in item.items():
                if type(key) is not str:
                    raise StrictJSONError(f"{where} contains a non-string object key")
                try:
                    encoded_key = key.encode("utf-8", errors="strict")
                except UnicodeEncodeError as exc:
                    raise StrictJSONError(f"{where} contains a lone surrogate object key") from exc
                if len(encoded_key) > MAX_STRING_BYTES:
                    raise StrictJSONError(f"{where} contains an oversized object key")
                account(len(encoded_key) + 3 + 5 * sum(ord(char) < 0x20 for char in key))
                children.append(child)
            pending.append((item, depth, True))
            pending.extend((child, depth + 1, False) for child in reversed(children))
        else:
            raise StrictJSONError(f"{where} contains unsupported value type {type(item).__name__}")


def loads(data: bytes | str, *, where: str = "JSON input") -> Any:
    if isinstance(data, str):
        try:
            raw = data.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise StrictJSONError(f"{where} contains a lone surrogate") from exc
    elif type(data) is bytes:
        raw = data
    else:
        raise StrictJSONError(f"{where} must be bytes or text")
    if len(raw) > MAX_JSON_BYTES:
        raise StrictJSONError(f"{where} exceeds {MAX_JSON_BYTES} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_int=_parse_integer,
            parse_float=_parse_float,
            parse_constant=_reject_constant,
        )
    except StrictJSONError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise StrictJSONError(f"invalid or over-nested {where}: {exc}") from exc
    validate_tree(value, where=where)
    return value


def read_bytes(path: Path, *, where: str = "JSON file") -> bytes:
    if path.is_symlink():
        raise StrictJSONError(f"{where} must not be a symlink")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
    except OSError as exc:
        raise StrictJSONError(f"cannot read {where}: {exc}") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise StrictJSONError(f"{where} {path} exceeds {MAX_JSON_BYTES} bytes")
    return raw


def load(path: Path, *, where: str = "JSON file") -> Any:
    return loads(read_bytes(path, where=where), where=f"{where} {path}")
