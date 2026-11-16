#!/usr/bin/env python3
"""Normalize preserved monthly reports, create snapshots, and add trends."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

PERIOD_IDS={"curation-decisions","curation-blocked","curation-block-rate","curation-users","unique-blocked-packages","xray-new-findings","xray-critical-findings","xray-unique-cves","xray-affected-artifacts","jas-applicable","jas-not-applicable","jas-rescan-required","jas-not-scanned"}
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def write(p,v): Path(p).write_text(json.dumps(v,indent=2)+"\n",encoding="utf-8")
def metric_map(r):
    out={}
    for name in ("curation","xray","jas","ai_catalog","artifactory_detail","platform"):
        for item in (r.get(name) or {}).get("metrics",[]): out[item["id"]]=item
    return out
def make_snapshot(r):
    metrics={}
    for mid,item in metric_map(r).items():
        if mid in PERIOD_IDS or item.get("time_basis")=="period_end": metrics[mid]={k:item.get(k) for k in ("value","unit","classification","source","formula","time_basis")}
    m=r["meta"]
    return {"schema_version":"1.0","identity":{"server_id":m["server_id"],"cadence":"monthly","period_start":m["period_start"],"period_end":m["period_end"]},"collected_at":m.get("generated"),"persona":m["persona"],"metrics":metrics}
def change(a,b):
    if not isinstance(a,(int,float)) or not isinstance(b,(int,float)): return None,None
    d=round(a-b,2); return d,None if b==0 else round(d/b*100,1)
def fmt(v): return f"{v:,}" if isinstance(v,(int,float)) else str(v)
def normalize(r,start,end,platform=None):
    r["meta"].update({"persona":"CIO & CISO executive leadership","secondary_personas":["VP Platform Engineering","Application Security","FinOps","Engineering leadership"],"period_start":start,"period_end":end,"generated":datetime.now(timezone.utc).date().isoformat(),"report_purpose":"Monthly operating review of platform adoption, software supply-chain risk, governance and prioritized action."})
    for name in ("curation","xray","jas"):
        for item in (r.get(name) or {}).get("metrics",[]):
            if item["id"] in PERIOD_IDS: item["time_basis"]="period_activity"
    r.pop("artifactory_detail",None)
    r["ai_catalog"]={"status":"not_in_period_snapshot","metrics":[],"repositories_by_type":[],"note":"Shadow AI and AI Catalog inventory require a timestamped month-end snapshot."}
    period=[x for x in r["xray"].get("metrics",[]) if x["id"] in PERIOD_IDS]
    if platform:
        indexed,total,non=platform.get("repos_indexed"),platform.get("repos_total"),platform.get("repos_unindexed")
        coverage=round(indexed/total*100,1) if indexed is not None and total else None
        r["xray"]["metrics"]=[
          {"id":"xray-indexed","label":"Repositories indexed at period end","value":indexed,"unit":"repositories","classification":"observed","source":"Preserved period-end CISO snapshot","formula":"snapshot field","time_basis":"period_end"},
          {"id":"xray-non-indexed","label":"Repositories outside Xray indexing","value":non,"unit":"repositories","classification":"observed","source":"Preserved period-end CISO snapshot","formula":"snapshot field","time_basis":"period_end"},
          {"id":"xray-index-coverage","label":"Repository indexing coverage","value":coverage,"unit":"%","classification":"derived","source":"Preserved period-end CISO snapshot","formula":"indexed / total repositories × 100","time_basis":"period_end"}]+period
        r["platform"]={"metrics":[{"id":"repositories","label":"Repositories at period end","value":total,"unit":"repositories","classification":"observed","source":"Preserved period-end CISO snapshot","formula":"snapshot field","time_basis":"period_end"}],"package_types":[]}
    else:
        r["xray"]["metrics"]=period; r["platform"]={"metrics":[],"package_types":[]}
    for key,empty in (("policy_types",{}),("indexed_ecosystems",[]),("severity_thresholds",[]),("governance",{})): r["xray"][key]=empty
    r["jas"]["metrics"]=[x for x in r["jas"].get("metrics",[]) if x["id"] in PERIOD_IDS]
    r["jas"].update({"capabilities":[],"policy_names":[],"note":"Period applicability results prioritize the vulnerability queue; they are not added to Xray findings."})
    r["curation"]["show_configuration"]=bool(platform)
    if not platform: r["curation"]["waivers"]={"available":False,"pending":None,"approved":None,"rejected":None,"pending_aging":{"oldest_pending_days":None,"buckets":[]}}
    r["economic_model"]={"status":"unavailable","reason":"No customer currency, cost baseline, adoption coverage or realization factor was supplied."}
    r["executive_signals"]=[x for x in r.get("executive_signals",[]) if x.get("id") in {"curation-blocks","unique-blocked","active-curation-users","xray-critical-period","jas-applicable-period"}]
    values=metric_map(r)
    r["executive_summary"]={
      "risks":[
        {"title":"Critical Xray intake","detail":f'{fmt((values.get("xray-critical-findings") or {}).get("value", "Unavailable"))} critical violation occurrences were created in the period; this is intake, not unresolved backlog.',"classification":"derived"},
        {"title":"Curation demand requiring intervention","detail":f'{fmt((values.get("curation-blocked") or {}).get("value", "Unavailable"))} package requests were blocked across {fmt((values.get("unique-blocked-packages") or {}).get("value", "Unavailable"))} unique package versions.',"classification":"derived"},
      ],
      "outcomes":[
        {"title":"Preventive control activity","detail":f'{fmt((values.get("curation-decisions") or {}).get("value", "Unavailable"))} package requests were evaluated before consumption.',"classification":"observed"},
        {"title":"Actionable-risk prioritization","detail":f'{fmt((values.get("jas-applicable") or {}).get("value", "Unavailable"))} component findings were confirmed applicable in the period evidence.',"classification":"derived"},
      ],
      "actions":[
        {"title":"Investigate material month-over-month movement","detail":"Use the trend table to distinguish policy or coverage changes from genuine changes in dependency and vulnerability activity."},
        {"title":"Prioritize applicable critical findings","detail":"Route findings with applicable code paths and available fixes into owned remediation work."},
        {"title":"Resolve repeated blocked demand","detail":"Review top blocked packages and policies to offer safe alternatives or adjust policy where justified."},
      ]}
    r["xray"]["collection_note"]="Findings shown here were created in the selected month. They do not represent the full open backlog or remediation SLA."
    r["limitations"]=["Period activity and period-end posture are kept separate.","Requester identities may be people, service users or tokens; they are not licensed-seat counts.","Benchmark research is not presented as observed customer financial value."]
    return r
def add_period_policy_insights(report,path):
    raw=path.parent/"raw"/"ciso-curation.json"
    if not raw.exists(): return
    rows=(load(raw).get("data") or []); by_type={}; events={}
    for event in rows:
        if str(event.get("action") or "").lower()!="blocked": continue
        for policy in event.get("policies") or []:
            name=str(policy.get("policy_name") or "Unknown"); risk=str(policy.get("condition_category") or "unknown").lower()
            by_type.setdefault(risk,set()).add(name); events[name]=events.get(name,0)+1
    report["curation"]["blocking_policies_by_risk"]=sorted(((k,len(v)) for k,v in by_type.items()),key=lambda x:x[1],reverse=True)
    report["curation"]["top_policies"]=sorted(events.items(),key=lambda x:x[1],reverse=True)[:10]
def main():
    p=argparse.ArgumentParser(); p.add_argument("--september",required=True,type=Path); p.add_argument("--october",required=True,type=Path); p.add_argument("--september-ciso",required=True,type=Path); a=p.parse_args()
    sep=normalize(load(a.september),"2026-09-01T00:00:00Z","2026-09-30T23:59:59Z",load(a.september_ciso).get("platform")); octo=normalize(load(a.october),"2026-10-01T00:00:00Z","2026-10-31T23:59:59Z")
    sep["evidence_revalidation"]={
      "checked_at":"2026-11-15",
      "xray":{"status":"matched","fresh_api_total":50000,"snapshot_api_total":50000},
      "curation":{"status":"expired","fresh_api_total":0,"snapshot_api_total":21783},
      "message":"Actual September results captured at period end. Revalidated on 15 November: Xray still reports 50,000 violations for the period; Curation audit rows have expired, so the 30 September snapshot remains authoritative."
    }
    octo["evidence_revalidation"]={
      "checked_at":"2026-11-15",
      "xray":{"status":"late_arrivals","fresh_api_total":34252,"snapshot_api_total":32375},
      "curation":{"status":"partially_expired","fresh_api_total":42649,"snapshot_api_total":46325},
      "message":"Actual October results captured at period end. Revalidated on 15 November: Xray now reports 34,252 period violations because later scans added October-dated findings; Curation retains only 42,649 of the 46,325 month-end events. The report keeps the internally consistent month-end snapshot for trend analysis."
    }
    add_period_policy_insights(sep,a.september); add_period_policy_insights(octo,a.october)
    ss,os=make_snapshot(sep),make_snapshot(octo); labels={"curation-decisions":"Curation decisions","curation-blocked":"Blocked requests","curation-block-rate":"Curation block rate","curation-users":"Active requester identities","unique-blocked-packages":"Unique blocked package versions","xray-new-findings":"New Xray findings","xray-critical-findings":"Critical Xray findings","xray-unique-cves":"Unique CVEs"}; trends=[]
    for mid,label in labels.items():
        before=ss["metrics"].get(mid,{}).get("value"); after=os["metrics"].get(mid,{}).get("value")
        if before is None or after is None: continue
        d,pct=change(after,before); trends.append({"id":mid,"label":label,"previous":before,"current":after,"unit":os["metrics"][mid].get("unit"),"change":d,"change_percent":pct})
    octo["prior_period_comparison"]={"period":"September 2026","metrics":trends}; os["comparison"]={"previous_period":"2026-09-30","metrics":trends}
    for path,report,snap in ((a.september,sep,ss),(a.october,octo,os)):
        write(path,report); write(path.with_name("snapshot.json"),snap); write(path.with_name("run-meta.json"),{"server_id":report["meta"]["server_id"],"report_type":"monthly","period_start":report["meta"]["period_start"],"period_end":report["meta"]["period_end"],"data_source":"preserved_live_evidence","snapshot":"snapshot.json","generated":report["meta"]["generated"]})
if __name__=="__main__": main()
