"""Prove the HDC core: encode two glyphs that differ only in price, then show
drift is concentrated at the role/segment that changed and ~0 elsewhere.

Run from server/:  ./.venv/bin/python -m app.hdc.examples.demo
"""

import copy
import json
from pathlib import Path

from app.hdc import encode_glyph, glyph_drift, teach


def fill(template: dict, values: dict[str, float | str]) -> dict:
    g = copy.deepcopy(template)
    for layer in g["layers"]:
        for seg in layer["segments"]:
            for role in seg["roles"]:
                role["value"] = values[role["key"]]
    return g


def main() -> None:
    template = json.loads((Path(__file__).parent / "equity.template.json").read_text())

    base_vals = {
        "price": 196.0, "volume": 1_200_000, "interval": "1m",
        "vs_sp500_pct": 0.4, "sector_volume": 5_000_000,
        "gold": 2_300, "silver": 29, "bitcoin": 68_000,
        "yahoo_rank": 7, "fed_tone": 6,
    }
    # t+1: only price ticks up slightly.
    next_vals = {**base_vals, "price": 197.5}

    _, nodes_a = encode_glyph(fill(template, base_vals))
    _, nodes_b = encode_glyph(fill(template, next_vals))

    print("drift after a small price tick (price 196.0 -> 197.5):\n")
    for path in [
        "cortex",
        "layer:symbol",
        "segment:symbol/price_action",
        "role:symbol/price_action/price",
        "role:symbol/price_action/volume",
        "layer:macro",
        "segment:macro/news_sentiment",
    ]:
        print(f"  {path:42s} {glyph_drift(nodes_a, nodes_b, path):.4f}")

    proto = None
    for _ in range(5):
        _, n = encode_glyph(fill(template, base_vals))
        proto = teach(proto, n["cortex"], lr=0.3)
    print("\nteach() built a temporal prototype; self-drift vs latest:",
          round(glyph_drift({"cortex": proto}, nodes_a, "cortex"), 4))


if __name__ == "__main__":
    main()
