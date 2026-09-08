"""TSO Portaria ANP 1/2003 adapters for programmed/actual meter volumes.

TAG, TBG, and NTS publish daily receipt/delivery quantities under the same
regulatory item (Portaria ANP nº 1/2003 Art. 2º I-h). Each adapter discovers
and fetches operator files, then normalizes to the lake ``flows_points``
shape with a ``source`` column (``tag`` / ``tbg`` / ``nts``).
"""
from __future__ import annotations

from .base import TSO_SOURCES, fetch_all, build_all_points, _load_adapters
from .merge import merge_points

__all__ = [
    "TSO_SOURCES",
    "fetch_all",
    "build_all_points",
    "merge_points",
    "adapters",
]


def adapters():
    return _load_adapters()
