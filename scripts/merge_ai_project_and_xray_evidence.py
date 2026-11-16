#!/usr/bin/env python3
"""Merge preserved Xray summaries and repository project ownership into AI evidence."""
import argparse, json
from collections import Counter
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--evidence",required=True,type=Path); p.add_argument("--storage",required=True,type=Path)
    p.add_argument("--xray-summary",action="append",default=[],type=Path); p.add_argument("--output",required=True,type=Path); a=p.parse_args()
    evidence=json.loads(a.evidence.read_text()); storage=json.loads(a.storage.read_text())
    projects={str(x.get("repoKey")):x.get("projectKey") for x in storage.get("repositoriesSummaryList") or [] if x.get("repoKey")}
    summaries=[]
    for path in a.xray_summary: summaries.extend((json.loads(path.read_text()).get("artifacts") or []))
    by_path={str(x.get("general",{}).get("path")):x for x in summaries}
    by_identity={(str(x.get("general",{}).get("component_id") or "").rsplit(":",1)[0],
                  str(x.get("general",{}).get("component_id") or "").rsplit(":",1)[-1]):x for x in summaries}
    inventory=evidence.setdefault("inventory",{})
    for kind in ("skills","plugins","mcp_servers","models"):
        group=inventory.get(kind) or {}; assets=group.get("visible_assets") or []
        for asset in assets:
            repo=asset.get("repository")
            if repo:
                project=projects.get(repo); asset["project_key"]=project
                asset["project_status"]="Unlinked" if project in (None,"","default") else "Linked"
            else: asset["project_status"]="Unknown"
            if kind=="skills":
                path=f'default/{repo}/{asset.get("artifact_path")}' if asset.get("artifact_path") else None
                artifact=(by_path.get(path) if path else None) or by_identity.get((str(asset.get("name")),str(asset.get("version"))))
                if artifact is not None:
                    issues=artifact.get("issues") or []; sev=Counter(str(x.get("severity") or "Unknown").lower() for x in issues)
                    asset.update({"vulnerability_status":"Vulnerable" if issues else "No known vulnerabilities","vulnerability_count":len(issues),
                                  "critical_vulnerabilities":sev.get("critical",0),"high_vulnerabilities":sev.get("high",0)})
                else:
                    asset.setdefault("vulnerability_status","No Xray data"); asset.setdefault("vulnerability_count",0)
        pc=Counter(x.get("project_status","Unknown").lower() for x in assets)
        group["project_counts"]={x:pc.get(x,0) for x in ("linked","unlinked","unknown")}
        if kind=="skills":
            vc=Counter(x.get("vulnerability_status","No Xray data").lower().replace(" ","_") for x in assets)
            group["vulnerability_counts"]={x:vc.get(x,0) for x in ("vulnerable","no_known_vulnerabilities","no_xray_data")}
    evidence["status"]="partial"
    evidence["collection_quality"]={"behavioral_status":"partial prior capture","dependency_xray_summaries":len(summaries),"skills_total":len((inventory.get("skills") or {}).get("visible_assets") or [])}
    evidence["limitations"]=["Behavioral counts are from the prior partial capture; the full live status refresh did not complete and must not be read as a complete count of suspicious skills.",
        "Behavioral status and dependency vulnerability posture are separate; approved does not mean vulnerability-free.",
        "Project attribution is the owning project on the backing repository; assets without repository evidence remain Unknown.",
        "Dependency posture is unavailable for skills not present in the preserved Xray artifact summaries; the vulnerable count is a verified minimum, not a complete estate total."]
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(evidence,indent=2)+"\n"); print(a.output)
if __name__=="__main__": main()
