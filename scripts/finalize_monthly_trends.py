#!/usr/bin/env python3
"""Rebuild snapshots and prior-period comparison from final enriched reports."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import prepare_historical_reports as history

LABELS={
    "curation-decisions":"Curation decisions","curation-blocked":"Blocked requests",
    "curation-block-rate":"Curation block rate","curation-users":"Curation unique users",
    "unique-blocked-packages":"Unique blocked package versions","xray-new-findings":"New Xray findings",
    "xray-critical-findings":"Critical Xray findings","xray-unique-cves":"Unique CVEs",
}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--september",required=True,type=Path); p.add_argument("--october",required=True,type=Path); a=p.parse_args()
    sep=history.load(a.september); octo=history.load(a.october)
    ss,os=history.make_snapshot(sep),history.make_snapshot(octo); trends=[]
    for mid,label in LABELS.items():
        before=ss["metrics"].get(mid,{}).get("value"); after=os["metrics"].get(mid,{}).get("value")
        if before is None or after is None: continue
        delta,pct=history.change(after,before)
        trends.append({"id":mid,"label":label,"previous":before,"current":after,
            "unit":os["metrics"][mid].get("unit"),"change":delta,"change_percent":pct})
    octo["prior_period_comparison"]={"period":"September 2026","metrics":trends}
    os["comparison"]={"previous_period":"2026-09-30","metrics":trends}
    history.write(a.september,sep); history.write(a.october,octo)
    history.write(a.september.with_name("snapshot.json"),ss); history.write(a.october.with_name("snapshot.json"),os)
    print(a.september); print(a.october)
if __name__=="__main__": main()
