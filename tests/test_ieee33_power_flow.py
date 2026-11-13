import importlib.util
from pathlib import Path
MODULE_PATH=Path(__file__).resolve().parents[1]/"scripts"/"run_ieee33bw_power_flow.py"
SPEC=importlib.util.spec_from_file_location("run_ieee33bw_power_flow",MODULE_PATH)
M=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)
CASE=Path(__file__).resolve().parents[1]/"data"/"electrical"/"ieee33bw_reference.json"

def test_reference_case_structure_and_power_flow():
    case=M.load_case(CASE); buses,closed,parent,_,order=M.build_radial_tree(case)
    assert len(buses)==33 and len(closed)==32 and len(order)==33
    assert sum(x["p_kw"] for x in case["bus"])==3715
    assert sum(x["q_kvar"] for x in case["bus"])==2300
    assert sum(not x["in_service"] for x in case["branch"])==5
    result=M.run_backward_forward_sweep(case)
    s=result["summary"]
    assert result["converged"]
    assert abs(s["active_power_balance_residual_mw"])<1e-7
    assert abs(s["reactive_power_balance_residual_mvar"])<1e-7
    assert 0.90 < s["minimum_voltage_pu"] < 1.0
    assert s["voltage_limit_violations"]==0
    reference=s["published_reference_comparison"]
    assert reference["active_loss_within_tolerance"]
    assert reference["minimum_voltage_within_tolerance"]
    assert reference["computed_minimum_voltage_bus"]==reference["reference_minimum_voltage_bus"]

def test_radial_validator_rejects_closed_tie_cycle():
    case=M.load_case(CASE)
    case["branch"][32]["in_service"]=True
    try: M.build_radial_tree(case)
    except ValueError as e: assert "cycle" in str(e).lower() or "spanning tree" in str(e).lower()
    else: raise AssertionError("Expected closed tie to invalidate radial base case")
