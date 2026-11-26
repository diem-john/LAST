"""QUBO formulation for the initial Bus-6 topology-restoration experiment.

The initial abstraction has three post-contingency network components and five
normally-open ties. The QUBO selects exactly C-1 ties, penalizes ties that are
internal to a component, and penalizes parallel ties between the same pair of
components. For this three-component case, these conditions yield a connected
tree. Electrical feasibility is checked separately by the grid validator.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from grid.reconfiguration import (
    build_post_contingency_network,
    get_normally_open_ties,
)


@dataclass(frozen=True)
class QUBO:
    variables: tuple[str, ...]
    branch_ids: tuple[int, ...]
    linear: tuple[float, ...]
    quadratic: tuple[tuple[float, ...], ...]
    offset: float
    metadata: dict

    def energy(self, bits) -> float:
        values = tuple(int(value) for value in bits)
        if len(values) != len(self.variables):
            raise ValueError(
                f"Expected {len(self.variables)} bits, received {len(values)}"
            )
        if any(value not in (0, 1) for value in values):
            raise ValueError("QUBO decisions must be binary (0 or 1)")
        result = float(self.offset)
        result += sum(self.linear[i] * values[i] for i in range(len(values)))
        result += sum(
            self.quadratic[i][j] * values[i] * values[j]
            for i in range(len(values))
            for j in range(i + 1, len(values))
        )
        return float(result)

    def to_dict(self) -> dict:
        return {
            "variables": list(self.variables),
            "branch_ids": list(self.branch_ids),
            "linear": list(self.linear),
            "quadratic": [list(row) for row in self.quadratic],
            "offset": self.offset,
            "metadata": self.metadata,
            "energy_convention": (
                "offset + sum_i linear[i]*x[i] + "
                "sum_{i<j} quadratic[i][j]*x[i]*x[j]"
            ),
        }


def build_tie_restoration_qubo(
    case: dict,
    faulted_buses=(6,),
    exact_closures: int | None = None,
    cardinality_penalty: float = 10.0,
    topology_penalty: float = 10.0,
    switching_costs: Mapping[int, float] | None = None,
) -> QUBO:
    """Build the compact QUBO for tie selection after the specified outage.

    The current implementation intentionally supports exactly three
    post-contingency components. A more general network requires additional
    connectivity/cycle constraints and should not silently reuse this encoding.
    """
    active_buses, surviving, components = build_post_contingency_network(
        case, faulted_buses
    )
    if len(components) != 3:
        raise ValueError(
            "Initial LAST-Q QUBO is derived for exactly 3 post-contingency "
            f"components; found {len(components)}"
        )
    target = len(components) - 1 if exact_closures is None else int(exact_closures)
    if target != 2:
        raise ValueError("Initial three-component QUBO requires exactly 2 tie closures")
    if cardinality_penalty <= 0 or topology_penalty <= 0:
        raise ValueError("Penalty weights must be positive")

    ties = get_normally_open_ties(case)
    component_of = {
        bus: index for index, component in enumerate(components) for bus in component
    }
    n = len(ties)
    branch_ids = tuple(int(tie["branch_id"]) for tie in ties)
    variables = tuple(
        f"tie_{int(tie['branch_id'])}_{int(tie['from_bus'])}_{int(tie['to_bus'])}"
        for tie in ties
    )
    linear = [cardinality_penalty * (1 - 2 * target) for _ in range(n)]
    quadratic = [[0.0 for _ in range(n)] for _ in range(n)]
    offset = cardinality_penalty * (target ** 2)

    # (sum_i x_i - target)^2
    for i in range(n):
        for j in range(i + 1, n):
            quadratic[i][j] += 2.0 * cardinality_penalty

    # A tie internal to one pre-existing component creates a cycle and cannot
    # reconnect the source-disconnected sections.
    internal_tie_ids = []
    component_pairs = {}
    for index, tie in enumerate(ties):
        u, v = int(tie["from_bus"]), int(tie["to_bus"])
        if u not in active_buses or v not in active_buses:
            linear[index] += topology_penalty
            internal_tie_ids.append(int(tie["branch_id"]))
            continue
        cu, cv = component_of[u], component_of[v]
        if cu == cv:
            linear[index] += topology_penalty
            internal_tie_ids.append(int(tie["branch_id"]))
        else:
            pair = tuple(sorted((cu, cv)))
            component_pairs.setdefault(pair, []).append(index)

    # Parallel ties between the same two components cannot both be closed in
    # a radial restoration topology.
    parallel_conflicts = []
    for pair, indices in component_pairs.items():
        for pos, i in enumerate(indices):
            for j in indices[pos + 1:]:
                quadratic[min(i, j)][max(i, j)] += topology_penalty
                parallel_conflicts.append(
                    [branch_ids[min(i, j)], branch_ids[max(i, j)]]
                )

    costs = switching_costs or {}
    for i, branch_id in enumerate(branch_ids):
        cost = float(costs.get(branch_id, 0.0))
        if cost < 0:
            raise ValueError("Switching costs must be non-negative")
        linear[i] += cost

    metadata = {
        "formulation": "bus6_three_component_tie_restoration",
        "faulted_buses": sorted(int(x) for x in faulted_buses),
        "post_contingency_components": [sorted(c) for c in components],
        "component_count": len(components),
        "required_tie_closures": target,
        "internal_tie_branch_ids_penalized": sorted(internal_tie_ids),
        "parallel_tie_conflicts_penalized": parallel_conflicts,
        "cardinality_penalty": float(cardinality_penalty),
        "topology_penalty": float(topology_penalty),
        "switching_costs": {str(k): float(v) for k, v in costs.items()},
        "scope": "topology-level QUBO; not an AC power-flow or operational optimizer",
    }
    return QUBO(
        variables=variables,
        branch_ids=branch_ids,
        linear=tuple(float(x) for x in linear),
        quadratic=tuple(tuple(float(x) for x in row) for row in quadratic),
        offset=float(offset),
        metadata=metadata,
    )
