import pytest

from grid.qaoa_resource_estimates import (
    estimate_x_mixer_resources,
    estimate_xy_mixer_resources,
)


def test_x_mixer_resource_estimate_matches_kernel_gate_structure():
    result = estimate_x_mixer_resources(variable_count=3, zz_edge_count=3, layers=2)
    assert result["qubit_count"] == 3
    assert result["single_qubit_gate_count"] == 3 + 2 * (2 * 3 + 3)
    assert result["two_qubit_gate_count"] == 2 * 3 * 2
    assert result["primitive_gate_count"] == 33
    assert result["source_order_depth_upper_bound"] == 1 + 2 * (2 + 3 * 3)


def test_xy_mixer_resource_estimate_includes_no_action_and_complete_graph():
    result = estimate_xy_mixer_resources(action_count=3, layers=2)
    # Four choices (no-action plus three actions) produce six mixer edges.
    assert result["qubit_count"] == 4
    assert result["mixer_edge_count"] == 6
    assert result["primitive_gate_count"] == 1 + 2 * (3 + 18 * 6)
    assert result["two_qubit_gate_count"] == 4 * 6 * 2
    assert result["single_qubit_gate_count"] + result["two_qubit_gate_count"] == result["primitive_gate_count"]


@pytest.mark.parametrize("function,args", [
    (estimate_x_mixer_resources, (-1, 0, 1)),
    (estimate_x_mixer_resources, (1, -1, 1)),
    (estimate_xy_mixer_resources, (-1, 1)),
    (estimate_xy_mixer_resources, (1, 0)),
])
def test_resource_estimates_reject_invalid_dimensions(function, args):
    with pytest.raises(ValueError):
        function(*args)
