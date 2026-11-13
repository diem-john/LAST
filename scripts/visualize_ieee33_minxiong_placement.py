"""Split geographic placement and abstract topology figures for Phase 5B."""
from __future__ import annotations
import argparse, json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PLACEMENT=ROOT/"data/geospatial/processed/minxiong_cluster_001_ieee33_synthetic.gpkg"
CLUSTERS=ROOT/"data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg"
ROADS=ROOT/"data/geospatial/raw/osm/roads/osm_chiayi_roads_edges.gpkg"
OUT_GEO=ROOT/"reports/geospatial/minxiong_cluster_001_ieee33_geographic_placement.png"
OUT_TOPO=ROOT/"reports/geospatial/ieee33_abstract_radial_topology.png"
OUT_JSON=ROOT/"reports/geospatial/minxiong_cluster_001_ieee33_spatial_review.json"
OUT_CSV=ROOT/"reports/geospatial/minxiong_cluster_001_ieee33_branch_review.csv"
CLUSTER_ID="Q05_cluster_001"
CRS="EPSG:3826"

def topology_layer_positions(bus_ids, edges):
    adjacency={int(n):set() for n in bus_ids}
    for a,b in edges:
        adjacency[int(a)].add(int(b)); adjacency[int(b)].add(int(a))
    if 1 not in adjacency: raise ValueError("Topology must contain root bus 1")
    depth={1:0}; queue=deque([1])
    while queue:
        n=queue.popleft()
        for m in sorted(adjacency[n]):
            if m not in depth: depth[m]=depth[n]+1; queue.append(m)
    if set(depth)!=set(adjacency): raise ValueError("Topology must be connected to bus 1")
    levels={}
    for n,d in depth.items(): levels.setdefault(d,[]).append(n)
    pos={}
    for d,nodes in levels.items():
        nodes.sort()
        for i,n in enumerate(nodes): pos[n]=(float(d),(len(nodes)-1)/2-i)
    return pos

def validate_layers(cluster,buses,branches):
    if len(cluster)!=1 or len(buses)!=33 or len(branches)!=32:
        raise ValueError("Expected one cluster, 33 buses, and 32 branches")
    if not {"bus_id","bus_role"}.issubset(buses.columns): raise ValueError("Missing bus fields")
    if not {"branch_id","from_bus","to_bus"}.issubset(branches.columns): raise ValueError("Missing branch fields")
    if sorted(buses.bus_id.astype(int).tolist())!=list(range(1,34)): raise ValueError("Bus IDs must be unique 1..33")
    if any(x.crs is None for x in (cluster,buses,branches)): raise ValueError("All layers require CRS")
    poly=cluster.to_crs(CRS).geometry.iloc[0]; bm=buses.to_crs(CRS)
    if not all(poly.covers(pt) for pt in bm.geometry): raise ValueError("Bus outside selected cluster")
    return {"bus_count":33,"branch_count":32,"bus_ids_complete_1_to_33":True,
      "all_bus_points_within_cluster":True,"unique_bus_coordinates":int(bm.geometry.nunique()),
      "minimum_pairwise_bus_separation_m":float(min(bm.geometry.iloc[i].distance(bm.geometry.iloc[j])
      for i in range(len(bm)) for j in range(i+1,len(bm))))}

def draw_geographic(poly,roads,buses,out):
    fig,ax=plt.subplots(figsize=(12,10),constrained_layout=True)
    roads.plot(ax=ax,color="#c7cbd1",linewidth=.48,alpha=.85,zorder=1)
    poly.boundary.plot(ax=ax,color="#30343b",linewidth=1.6,zorder=2)
    buses.plot(ax=ax,color="#d1495b",markersize=38,edgecolor="white",linewidth=.6,zorder=3)
    for row in buses.itertuples():
        ax.annotate(str(int(row.bus_id)),(row.geometry.x,row.geometry.y),xytext=(3,3),
                    textcoords="offset points",fontsize=7,color="#20242a",zorder=4)
    ax.set_title("Synthetic IEEE 33-Bus Geographic Placement\nQ05_cluster_001 | Minxiong Township, Chiayi County",fontsize=14)
    ax.set_xlabel("Easting (m) — EPSG:3826"); ax.set_ylabel("Northing (m) — EPSG:3826")
    ax.set_aspect("equal"); ax.grid(True,linewidth=.35,alpha=.35)
    ax.text(.01,.01,"Synthetic benchmark coordinates; OSM roads are contextual only. No feeder routes or electrical connections depicted.",
            transform=ax.transAxes,fontsize=8,va="bottom",bbox={"facecolor":"white","alpha":.88,"edgecolor":"none"})
    fig.savefig(out,dpi=300,bbox_inches="tight"); plt.close(fig)

def draw_topology(buses,branches,out):
    ids=sorted(buses.bus_id.astype(int).tolist())
    edges=[(int(x.from_bus),int(x.to_bus)) for x in branches.itertuples()]
    pos=topology_layer_positions(ids,edges)
    fig,ax=plt.subplots(figsize=(15,9),constrained_layout=True)
    for a,b in edges:
        x1,y1=pos[a]; x2,y2=pos[b]; ax.plot([x1,x2],[y1,y2],color="#2878b5",linewidth=1.35,zorder=1)
    for n,(x,y) in pos.items():
        ax.scatter(x,y,s=420,color="#d1495b",edgecolors="white",linewidths=1,zorder=2)
        ax.text(x,y,str(n),ha="center",va="center",color="white",fontsize=8,fontweight="bold",zorder=3)
    ax.set_title("IEEE 33-Bus Standard Radial Benchmark — Abstract Topology",fontsize=15)
    ax.set_xlabel("Topological depth from Bus 1 (schematic; not distance)")
    ax.set_ylabel("Schematic node arrangement (not geographic)")
    ax.set_xticks(sorted({v[0] for v in pos.values()})); ax.set_yticks([])
    ax.grid(axis="x",linewidth=.35,alpha=.35); ax.spines[["top","right","left"]].set_visible(False)
    ax.text(.01,.01,"Abstract IEEE 33-bus adjacency only. Node positions and edge lengths have no geographic or electrical meaning.",
      transform=ax.transAxes,fontsize=8,va="bottom",bbox={"facecolor":"white","alpha":.9,"edgecolor":"none"})
    fig.savefig(out,dpi=300,bbox_inches="tight"); plt.close(fig)
    return {"layout":"breadth_first_topological_depth","root_bus":1,"edge_count":len(edges),"coordinates_are_geographic":False}

def create_review(placement=PLACEMENT,clusters=CLUSTERS,roads=ROADS,out_geo=OUT_GEO,out_topo=OUT_TOPO,out_json=OUT_JSON,out_csv=OUT_CSV):
    for path in (placement,clusters,roads):
        if not path.is_file(): raise FileNotFoundError(f"Required input not found: {path}")
    buses=gpd.read_file(placement,layer="synthetic_bus_locations")
    branches=gpd.read_file(placement,layer="synthetic_topology_connectors")
    allc=gpd.read_file(clusters,layer="analytical_urban_clusters")
    selected=allc.loc[allc.cluster_id.astype(str)==CLUSTER_ID].copy()
    if len(selected)!=1: raise ValueError(f"Expected one frozen cluster {CLUSTER_ID}")
    roadsdf=gpd.read_file(roads,layer="osm_chiayi_roads_edges")
    checks=validate_layers(selected,buses,branches)
    poly=selected.to_crs(CRS); bm=buses.to_crs(CRS)
    rm=roadsdf.to_crs(CRS); clipped=rm.loc[rm.geometry.intersects(poly.geometry.iloc[0])].copy()
    clipped.geometry=clipped.geometry.intersection(poly.geometry.iloc[0]); clipped=clipped.loc[~clipped.geometry.is_empty].copy()
    for f in (out_geo,out_topo,out_json,out_csv): f.parent.mkdir(parents=True,exist_ok=True)
    draw_geographic(poly,clipped,bm,out_geo)
    topo_info=draw_topology(buses,branches,out_topo)
    pd.DataFrame([{"branch_id":int(x.branch_id),"from_bus":int(x.from_bus),"to_bus":int(x.to_bus),
      "straight_line_connector_length_m":float(x.geometry.length),"length_is_conductor_length":False,
      "semantics":"between_synthetic_bus_coordinates_only"} for x in branches.to_crs(CRS).itertuples()]).to_csv(out_csv,index=False,encoding="utf-8-sig")
    report={"schema_version":"1.1","generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "status":"phase_5b_split_visualizations_generated","study_area":{"cluster_id":CLUSTER_ID,"crs":CRS},
      "validation":checks,"visualization_design":{"geographic_map":"bus points, boundary, contextual roads; no topology connectors",
      "abstract_topology_map":topo_info,"reason":"Geographic coordinates and abstract branch adjacency were generated independently; separate figures prevent straight-line overlays from being mistaken for feeder routes."},
      "connector_geometry_review":{"status":"diagnostic_only","interpretation":"Previous 158 nonincident crossings are cartographic only; they do not justify bus relocation or topology changes."},
      "outputs":{"geographic_map":str(out_geo),"abstract_topology_map":str(out_topo),"branch_review_csv":str(out_csv)},
      "limitations":["Bus coordinates are synthetic, not actual Taipower assets or verified loads.",
      "OSM roads are context, not electrical corridors.","Abstract topology layout has no geographic meaning.",
      "Straight-line coordinate distances are not conductor lengths or impedances.",
      "No electrical power-flow, protection, reliability, islanding, BESS, or operational feasibility is validated."],
      "decision_status":"split_figures_generated_human_acceptance_pending"}
    out_json.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--placement",type=Path,default=PLACEMENT); ap.add_argument("--clusters",type=Path,default=CLUSTERS)
    ap.add_argument("--roads",type=Path,default=ROADS); ap.add_argument("--output-geographic-map",type=Path,default=OUT_GEO)
    ap.add_argument("--output-topology-map",type=Path,default=OUT_TOPO); ap.add_argument("--output-review",type=Path,default=OUT_JSON)
    ap.add_argument("--output-csv",type=Path,default=OUT_CSV); a=ap.parse_args()
    r=create_review(a.placement.resolve(),a.clusters.resolve(),a.roads.resolve(),a.output_geographic_map.resolve(),
      a.output_topology_map.resolve(),a.output_review.resolve(),a.output_csv.resolve())
    print(json.dumps({"status":r["status"],"cluster_id":CLUSTER_ID,"bus_count":r["validation"]["bus_count"],
      "branch_count":r["validation"]["branch_count"],"minimum_pairwise_bus_separation_m":r["validation"]["minimum_pairwise_bus_separation_m"],
      "geographic_map":r["outputs"]["geographic_map"],"abstract_topology_map":r["outputs"]["abstract_topology_map"],
      "review_json":str(a.output_review.resolve()),"branch_review_csv":r["outputs"]["branch_review_csv"],
      "decision_status":r["decision_status"]},indent=2))
if __name__=="__main__": raise SystemExit(main())
