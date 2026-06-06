"""Compile a glyph JSON instance into a cortex vector + every sub-vector.

Hierarchy: role = bind(role_key, value); segment = bundle(roles);
layer = bundle(bind(seg_key, segment)); cortex = bundle(bind(layer_key, layer)).
Binding each child with its own key before bundling keeps every level
individually recoverable and comparable across time.
"""

from __future__ import annotations

import numpy as np

from .core import DIM, bind, bundle, drift, hv


def _encode_value(role: dict, dim: int) -> np.ndarray:
    if role.get("type", "symbol") == "scalar":
        lo, hi = role.get("range", [0.0, 1.0])
        from .core import encode_scalar

        return encode_scalar(role.get("value"), float(lo), float(hi), dim)
    return hv("val:" + str(role.get("value")), dim)


def encode_glyph(glyph: dict) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Return (cortex_vector, nodes) where nodes maps path -> own vector.

    Node paths: "cortex", "layer:<L>", "segment:<L>/<S>", "role:<L>/<S>/<R>".
    """
    dim = int(glyph.get("dim", DIM))
    nodes: dict[str, np.ndarray] = {}
    layer_terms: list[np.ndarray] = []
    layer_weights: list[float] = []

    for layer in glyph.get("layers", []):
        seg_terms: list[np.ndarray] = []
        seg_weights: list[float] = []

        for seg in layer.get("segments", []):
            role_vecs: list[np.ndarray] = []
            role_weights: list[float] = []
            for role in seg.get("roles", []):
                role_hv = bind(hv("role:" + role["key"], dim), _encode_value(role, dim))
                nodes[f"role:{layer['key']}/{seg['key']}/{role['key']}"] = role_hv
                role_vecs.append(role_hv)
                role_weights.append(float(role.get("weight", 1.0)))

            seg_hv = bundle(role_vecs, role_weights) if role_vecs else np.zeros(dim, np.float32)
            nodes[f"segment:{layer['key']}/{seg['key']}"] = seg_hv
            seg_terms.append(bind(hv("seg:" + seg["key"], dim), seg_hv))
            seg_weights.append(float(seg.get("weight", 1.0)))

        layer_hv = bundle(seg_terms, seg_weights) if seg_terms else np.zeros(dim, np.float32)
        nodes[f"layer:{layer['key']}"] = layer_hv
        layer_terms.append(bind(hv("layer:" + layer["key"], dim), layer_hv))
        layer_weights.append(float(layer.get("weight", 1.0)))

    cortex = bundle(layer_terms, layer_weights) if layer_terms else np.zeros(dim, np.float32)
    nodes["cortex"] = cortex
    return cortex, nodes


def glyph_drift(nodes_a: dict[str, np.ndarray], nodes_b: dict[str, np.ndarray], path: str = "cortex") -> float:
    """Drift between two encoded glyphs at any level (default: whole cortex)."""
    return drift(nodes_a[path], nodes_b[path])
