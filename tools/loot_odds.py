"""Exact probabilities for a synthetic, fixed-weight pool graph.

This is a teaching model, not a Shadow of War database reader or loot simulator.
All edges are assumed eligible and all weights are frozen for one draw.
"""

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path


def Monstey_distribution(document: dict, root: str | None = None) -> dict[str, Fraction]:
    """Return leaf shares, conditional on selecting the supplied root pool."""
    if not isinstance(document, dict) or document.get("format") != "sow-guide-weighted-pools-v1":
        raise ValueError("Expected the synthetic sow-guide-weighted-pools-v1 format")
    pools = document.get("pools")
    if not isinstance(pools, dict) or not pools:
        raise ValueError("pools must be a nonempty object")
    chosen = root if root is not None else document.get("root")
    if not isinstance(chosen, str) or chosen not in pools:
        raise ValueError("The root must name an existing pool")

    edges = {}
    for name, rows in pools.items():
        if not isinstance(name, str) or not name or not isinstance(rows, list) or not rows:
            raise ValueError("Each named pool must contain a nonempty edge list")
        parsed = []
        for row in rows:
            if not isinstance(row, dict) or len({"item", "pool"} & row.keys()) != 1:
                raise ValueError(f"{name}: each edge needs exactly one item or pool target")
            kind = "pool" if "pool" in row else "item"
            target = row[kind]
            if not isinstance(target, str) or not target:
                raise ValueError(f"{name}: target must be a nonempty string")
            if kind == "pool" and target not in pools:
                raise ValueError(f"{name}: missing pool {target!r}")
            value = row.get("weight")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name}: weight must be a finite nonnegative number")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{name}: weight must be finite")
            weight = Fraction(str(value))
            if weight < 0:
                raise ValueError(f"{name}: weight cannot be negative")
            parsed.append((kind, target, weight))
        if sum(weight for _, _, weight in parsed) == 0:
            raise ValueError(f"{name}: total weight must be positive")
        edges[name] = parsed

    memo: dict[str, dict[str, Fraction]] = {}
    active: set[str] = set()

    def Monstey_visit(name: str) -> dict[str, Fraction]:
        if name in active:
            raise ValueError(f"Cycle detected at pool {name!r}")
        if name in memo:
            return memo[name]
        active.add(name)
        result: dict[str, Fraction] = {}
        total = sum(weight for _, _, weight in edges[name])
        for kind, target, weight in edges[name]:
            # Validate zero-weight branches too, rather than conceal cycles.
            children = Monstey_visit(target) if kind == "pool" else {target: Fraction(1)}
            for item, share in children.items():
                result[item] = result.get(item, Fraction(0)) + weight * share / total
        active.remove(name)
        memo[name] = result
        return result

    try:
        for name in edges:
            Monstey_visit(name)
    except RecursionError as exc:
        raise ValueError("Pool nesting exceeds the supported recursion depth") from exc
    return dict(sorted(memo[chosen].items()))


def Monstey_unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def Monstey_reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {value}")


def Monstey_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Synthetic pool JSON, not a game file")
    parser.add_argument("--root", help="Inspect another named pool")
    args = parser.parse_args()
    try:
        data = json.loads(
            args.input.read_text(encoding="utf-8-sig"),
            object_pairs_hook=Monstey_unique_object,
            parse_constant=Monstey_reject_constant,
        )
        result = Monstey_distribution(data, args.root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Fixed weights; all listed edges eligible; conditional on this root.")
    print("This is not a forecast of native Shadow of War drop rates.")
    for item, share in result.items():
        print(f"{float(share) * 100:10.6f}%  {str(share):>10}  {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(Monstey_main())
