"""Deeply immutable JSON containers for frozen scientific contracts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Any


class FrozenDict(Mapping[str, Any]):
    """A read-only mapping with no mutable ``dict`` base-class escape hatch.

    Subclassing :class:`dict` is insufficient for a scientific contract:
    ``dict.__setitem__(instance, ...)`` bypasses an overridden ``__setitem__``.
    The backing dictionary is therefore held behind ``MappingProxyType`` and the
    public container implements only the read-only ``Mapping`` protocol.
    """

    __slots__ = ("_data",)

    def __init__(self, values: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_data", MappingProxyType(dict(values)))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenDict({dict(self._data)!r})"

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("scientific contract JSON is immutable")


def deep_freeze_json(value: Any) -> Any:
    """Recursively convert JSON objects and arrays to immutable containers."""
    if isinstance(value, dict):
        return FrozenDict({key: deep_freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(deep_freeze_json(item) for item in value)
    if isinstance(value, tuple):
        return tuple(deep_freeze_json(item) for item in value)
    return value


def deep_thaw_json(value: Any) -> Any:
    """Return ordinary JSON containers for wire serialization."""
    if isinstance(value, Mapping):
        return {key: deep_thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [deep_thaw_json(item) for item in value]
    return value
