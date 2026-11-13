"""Run a balanced three-phase backward/forward-sweep power flow for IEEE 33-bus case33bw."""
from __future__ import annotations
import argparse, csv, json, math
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CASE=ROOT/"data/electrical/ieee33bw_reference.json"
OUT=ROOT/"reports/electrical"
SQRT3=math.sqrt(3.0)

def load_case(path):
    case=json.loads(path.read_text(encoding="utf-8"))
    return case

def build_radial_tree(case):
    buses={int(x["bus_id"]):x for x in case["bus"]}
    if len(buses)!=33 or set(buses)!=set(range(1,34)): raise ValueError("Expected bus IDs 1..33 exactly once")
    closed=[x for x in case["branch"] if x["in_service"]]
    if len(closed)!=32: raise ValueError("Base case must have exactly 32 in-service branches")
    adj=defaultdict(list)
    for br in closed:
        a,b=int(br["from_bus"]),int(br["to_bus"])
        if a not in buses or b not in buses or a==b: raise ValueError("Invalid branch endpoints")
        adj[a].append((b,br)); adj[b].append((a,br))
    parent={1:None}; parent_branch={}; order=[]; q=deque([1])
    while q:
        n=q.popleft(); order.append(n)
        for m,br in sorted(adj[n],key=lambda t:t[0]):
            if m==parent[n]: continue
            if m in parent: raise ValueError("Closed network contains a cycle")
            parent[m]=n; parent_branch[m]=br; q.append(m)
    if set(parent)!=set(buses): raise ValueError("Closed network is disconnected")
    if len(closed)!=len(buses)-1: raise ValueError("Closed network is not a spanning tree")
    return buses,closed,parent,parent_branch,order

def run_backward_forward_sweep(case,tolerance=1e-10,max_iterations=1000):
    base=case["base"]; sbase=float(base["s_base_mva"]); vbase=float(base["v_base_kv_ll"])
    zbase=(vbase*vbase)/sbase
    buses,branches,parent,parent_branch,order=build_radial_tree(case)
    children=defaultdict(list)
    for bus,p in parent.items():
        if p is not None: children[p].append(bus)
    zpu={int(br["branch_id"]):complex(float(br["r_ohm"]),float(br["x_ohm"]))/zbase for br in branches}
    sp_load={n:complex(float(buses[n]["p_kw"]),float(buses[n]["q_kvar"]))/(1000*sbase) for n in buses}
    v={n:complex(float(buses[n].get("v_initial_pu",1.0)),0) for n in buses}
    v[1]=complex(float(base["slack_voltage_pu"]),0)
    converged=False; branch_i={}
    for iteration in range(1,max_iterations+1):
        inj={n:(sp_load[n]/v[n]).conjugate() for n in buses if n!=1}
        subtree=dict(inj); branch_i={}
        for n in reversed(order[1:]):
            p=parent[n]; br=parent_branch[n]; bid=int(br["branch_id"])
            branch_i[bid]=subtree[n]
            subtree[p]=subtree.get(p,0j)+subtree[n]
        v_new={1:v[1]}
        for n in order[1:]:
            p=parent[n]; br=parent_branch[n]; bid=int(br["branch_id"])
            v_new[n]=v_new[p]-zpu[bid]*branch_i[bid]
        err=max(abs(v_new[n]-v[n]) for n in buses)
        v=v_new
        if err<tolerance:
            converged=True; break
    if not converged: raise RuntimeError(f"Power flow did not converge in {max_iterations} iterations; last max voltage change={err}")
    # Recompute currents at converged voltages and branch complex powers.
    inj={n:(sp_load[n]/v[n]).conjugate() for n in buses if n!=1}
    subtree=dict(inj); branch_i={}
    for n in reversed(order[1:]):
        p=parent[n]; bid=int(parent_branch[n]["branch_id"])
        branch_i[bid]=subtree[n]; subtree[p]=subtree.get(p,0j)+subtree[n]
    branch_rows=[]; total_loss=0j
    for br in branches:
        bid=int(br["branch_id"]); current=branch_i[bid]; loss=(abs(current)**2)*zpu[bid]
        total_loss+=loss
        a=int(br["from_bus"]); b=int(br["to_bus"])
        # MATPOWER case33bw closed branches are oriented parent-to-child.
        if parent[b]==a: upstream=a; downstream=b
        elif parent[a]==b: upstream=b; downstream=a
        else: raise ValueError("Unexpected tree edge orientation")
        s_from=v[upstream]*current.conjugate()*sbase
        branch_rows.append({"branch_id":bid,"from_bus":a,"to_bus":b,"p_from_mw":s_from.real,
          "q_from_mvar":s_from.imag,"current_pu":abs(current),"loss_p_mw":loss.real*sbase,
          "loss_q_mvar":loss.imag*sbase,"in_service":True})
    slack_s=(sp_load[1]+subtree[1])*sbase
    bus_rows=[]
    for n in sorted(buses):
        row=buses[n]; vm=abs(v[n]); va=math.degrees(math.atan2(v[n].imag,v[n].real))
        bus_rows.append({"bus_id":n,"bus_type":row["bus_type"],"p_load_mw":sp_load[n].real*sbase,
          "q_load_mvar":sp_load[n].imag*sbase,"vm_pu":vm,"va_deg":va,
          "vmin_pu":float(row["v_min_pu"]),"vmax_pu":float(row["v_max_pu"]),
          "voltage_limit_ok":float(row["v_min_pu"])-1e-9<=vm<=float(row["v_max_pu"])+1e-9})
    p_load=sum(x["p_load_mw"] for x in bus_rows); q_load=sum(x["q_load_mvar"] for x in bus_rows)
    p_loss=total_loss.real*sbase; q_loss=total_loss.imag*sbase
    return {"converged":True,"iterations":iteration,"max_voltage_change_pu":err,"bus_results":bus_rows,
      "branch_results":branch_rows,"summary":{"bus_count":len(buses),"closed_branch_count":len(branches),
      "normally_open_tie_count":sum(1 for x in case["branch"] if not x["in_service"]),
      "total_load_mw":p_load,"total_load_mvar":q_load,"slack_p_mw":slack_s.real,
      "slack_q_mvar":slack_s.imag,"active_loss_mw":p_loss,"reactive_loss_mvar":q_loss,
      "minimum_voltage_pu":min(x["vm_pu"] for x in bus_rows),
      "minimum_voltage_bus":min(bus_rows,key=lambda x:x["vm_pu"])["bus_id"],
      "maximum_voltage_pu":max(x["vm_pu"] for x in bus_rows),
      "voltage_limit_violations":sum(not x["voltage_limit_ok"] for x in bus_rows),
      "active_power_balance_residual_mw":slack_s.real-p_load-p_loss,
      "reactive_power_balance_residual_mvar":slack_s.imag-q_load-q_loss}}

def write_outputs(case,result,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/"ieee33bw_power_flow.json").write_text(json.dumps({"generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "case_id":case["case_id"],"source":case["source"],"base":case["base"],"solver":"balanced_three_phase_backward_forward_sweep",
      "result":result},indent=2)+"\n",encoding="utf-8")
    for key,filename in [("bus_results","ieee33bw_bus_results.csv"),("branch_results","ieee33bw_branch_results.csv")]:
        with (outdir/filename).open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=list(result[key][0])); w.writeheader(); w.writerows(result[key])
    return outdir

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--case",type=Path,default=DEFAULT_CASE)
    ap.add_argument("--output-dir",type=Path,default=OUT); a=ap.parse_args()
    case=load_case(a.case); result=run_backward_forward_sweep(case); write_outputs(case,result,a.output_dir)
    print(json.dumps({"status":"power_flow_converged" if result["converged"] else "failed",
      "iterations":result["iterations"],**result["summary"],"output_dir":str(a.output_dir.resolve())},indent=2))
if __name__=="__main__": main()
