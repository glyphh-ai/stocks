"""Core HDC primitives: one bipolar-dense vector space, all simple functions.

Atomic vectors are bipolar {-1, +1}; composed vectors are real-valued
weighted sums in the same space. Everything is deterministic: a given name
always maps to the same hypervector, which is what makes cross-time drift
comparison meaningful.
"""

from __future__ import annotations

import hashlib

import numpy as np

DIM = 10_000


def _seed(name: str) -> int:
    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def hv(name: str, dim: int = DIM) -> np.ndarray:
    """Deterministic bipolar hypervector for a symbolic name."""
    rng = np.random.default_rng(_seed(name))
    return (rng.integers(0, 2, size=dim, dtype=np.int8) * 2 - 1).astype(np.float32)


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Key/value glue: elementwise multiply. Result is dissimilar to both."""
    return a * b


def bundle(vectors, weights=None) -> np.ndarray:
    """Superpose children into a parent that stays similar to each.

    This is where teach weights live: pass per-child importance weights.
    """
    arr = np.asarray(vectors, dtype=np.float32)
    if weights is None:
        return arr.sum(axis=0)
    w = np.asarray(weights, dtype=np.float32).reshape(-1, 1)
    return (arr * w).sum(axis=0)


# Global level basis: shared across all scalar roles so that nearby normalized
# values map to similar vectors. Role identity is restored by binding with the
# role key, so two different roles never collide.
_LEVEL_BASE = "__hdc_level_base__"
_LEVEL_PERM = "__hdc_level_perm__"


def _level_perm(dim: int) -> np.ndarray:
    rng = np.random.default_rng(_seed(_LEVEL_PERM))
    return rng.permutation(dim)


def encode_scalar(value: float, lo: float, hi: float, dim: int = DIM) -> np.ndarray:
    """Level-encode a scalar so adjacent values yield similar vectors."""
    base = hv(_LEVEL_BASE, dim).copy()
    frac = 0.0 if hi == lo else (float(value) - lo) / (hi - lo)
    frac = min(1.0, max(0.0, frac))
    nflip = int(round(frac * dim))
    if nflip:
        base[_level_perm(dim)[:nflip]] *= -1
    return base


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def drift(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine distance in [0, 2]; 0 = identical direction."""
    return 1.0 - cosine(a, b)


def teach(prototype: np.ndarray | None, glyph_vec: np.ndarray, lr: float = 0.1) -> np.ndarray:
    """Temporal EMA prototype: fold a new glyph into a running memory."""
    if prototype is None:
        return glyph_vec.astype(np.float32).copy()
    return ((1.0 - lr) * prototype + lr * glyph_vec).astype(np.float32)
