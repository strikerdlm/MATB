# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License: CeCILL, version 2.1 (see the LICENSE file).

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

_T = TypeVar("_T")


def unique_in_order(values: Iterable[_T]) -> tuple[_T, ...]:
    """Return unique hashable values in deterministic first-occurrence order."""
    return tuple(dict.fromkeys(values))
