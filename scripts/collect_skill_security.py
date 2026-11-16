#!/usr/bin/env python3
"""Collect current skill behavior, dependency risk and project attribution."""
from __future__ import annotations
import argparse, json, re, subprocess, tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

def jf(server_id, path, data=None, content_type=None):
    command = ["jf", "api", "--server-id", server_id]
    temp_path = None
    if data is not None:
        if content_type == "text/plain":
            command += ["-X", "POST", "--data", data]
        else:
            handle = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json")
            handle.write(data); handle.close(); temp_path = Path(handle.name)
            command += ["-X", "POST", "--input", str(temp_path)]
        if content_type: command += ["-H", f"Content-Type: {content_type}"]
    command.append(path)
    try:
        result=subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            detail=(result.stderr or result.stdout or "JFrog CLI returned no diagnostic").strip()
            raise RuntimeError(f"{path} failed: {detail}")
        return json.loads(result.stdout)
    finally:
        if temp_path: temp_path.unlink(missing_ok=True)

def version_key(value):
    return tuple((0, int(x)) if x.isdigit() else (1, x.lower()) for x in re.split(r"[.+_-]", str(value or "0")))

def display_status(raw):
    value = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    return {"APPROVED":"Not malicious","NOT_MALICIOUS":"Not malicious","MALICIOUS":"Malicious",
            "SUSPICIOUS":"Suspicious","SCANNING":"Scanning","SCAN_IN_PROGRESS":"Scanning","IN_PROGRESS":"Scanning","PENDING":"Scanning",
            "NOT_SCANNED":"Not scanned","UNSCANNED":"Not scanned","XRAY_DISABLED_FOR_REPO":"Not scanned",
            "UNKNOWN":"Not scanned", "":"Not scanned"}.get(value, value.replace("_", " ").title())

def classify_project_assignment(project_key, visible_project_keys):
    if project_key in visible_project_keys:
        return "Linked", [project_key]
    if project_key in (None, "", "default"):
        return "Unlinked", []
    return "Unknown", []

def main():
    p=argparse.ArgumentParser(); p.add_argument("--server-id",required=True); p.add_argument("--evidence",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path); p.add_argument("--aql-input",type=Path); p.add_argument("--storage",type=Path,
        help="Optional historical fallback only; live collection resolves current repository assignments from official APIs")
    p.add_argument("--all-skills",action="store_true"); p.add_argument("--workers",type=int,default=8); args=p.parse_args()
    evidence=json.loads(args.evidence.read_text()); prior=set((((evidence.get("inventory") or {}).get("skills") or {}).get("visible_names") or []))
    if args.aql_input: payload=json.loads(args.aql_input.read_text())
    else:
        aql='items.find({"@skill.name":{"$match":"*"},"type":"file"}).include("repo","path","name","property.*").limit(5000)'
        payload=jf(args.server_id,"/artifactory/api/search/aql",aql,"text/plain")
    candidates=[]
    for item in payload.get("results") or []:
        props={r.get("key"):r.get("value") for r in item.get("properties") or []}; name=props.get("skill.name")
        if not name or (not args.all_skills and prior and name not in prior): continue
        candidates.append({"name":name,"version":props.get("skill.version") or "Unavailable","repo":item.get("repo"),
            "artifact_path":"/".join(x for x in (item.get("path"),item.get("name")) if x and x!=".")})
    latest={}
    for item in candidates:
        identity=(item["name"],item["repo"]); current=latest.get(identity)
        if current is None or version_key(item["version"])>version_key(current["version"]): latest[identity]=item
    project_payload=jf(args.server_id,"/access/api/v1/projects")
    project_rows=project_payload.get("projects") if isinstance(project_payload,dict) else project_payload
    visible_project_keys={str(x.get("project_key") or x.get("projectKey")) for x in (project_rows or []) if x.get("project_key") or x.get("projectKey")}
    repository_keys=sorted({x["repo"] for x in latest.values() if x.get("repo")})
    repository_projects={}
    def repository_assignment(repo):
        config=jf(args.server_id,f'/artifactory/api/repositories/{quote(repo,safe="")}')
        return repo, config.get("projectKey")
    with ThreadPoolExecutor(max_workers=max(1,args.workers)) as pool:
        futures=[pool.submit(repository_assignment,repo) for repo in repository_keys]
        for future in as_completed(futures):
            repo,project=future.result(); repository_projects[repo]=project
    if args.storage:
        storage=json.loads(args.storage.read_text())
        for row in storage.get("repositoriesSummaryList") or []:
            repository_projects.setdefault(str(row.get("repoKey")),row.get("projectKey"))
    def project_evidence(repo):
        key=repository_projects.get(repo)
        status,linked=classify_project_assignment(key,visible_project_keys)
        return key,status,linked
    def collect(item):
        endpoint=f'/artifactory/api/skills/{quote(item["repo"],safe="")}/xrayStatus?path={quote(item["artifact_path"],safe="")}'
        raw=jf(args.server_id,endpoint).get("status"); project,status,linked=project_evidence(item["repo"])
        return {"name":item["name"],"version":item["version"],"repository":item["repo"],"artifact_path":item["artifact_path"],
                "security_status":display_status(raw),"raw_status":raw,"project_key":project,"project_status":status,
                "linked_projects":linked,"project_evidence_basis":"backing repository assignment"}
    assets=[]
    with ThreadPoolExecutor(max_workers=max(1,args.workers)) as pool:
        futures=[pool.submit(collect,item) for item in latest.values()]
        for future in as_completed(futures): assets.append(future.result())
    # Persist behavior results before the independent Xray lookup so a later
    # Xray failure cannot discard successfully collected statuses.
    checkpoint=dict(evidence); checkpoint_inventory=dict(evidence.get("inventory") or {})
    checkpoint_skills=dict(checkpoint_inventory.get("skills") or {}); checkpoint_skills["visible_assets"]=assets
    checkpoint_skills["status"]="partial"; checkpoint_skills.pop("reason",None)
    checkpoint_inventory["skills"]=checkpoint_skills; checkpoint["inventory"]=checkpoint_inventory
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(checkpoint,indent=2)+"\n")
    paths=[f'default/{x["repository"]}/{x["artifact_path"]}' for x in assets]
    artifacts=[]
    for start in range(0,len(paths),20):
        response=jf(args.server_id,"/xray/api/v2/summary/artifact",json.dumps({"paths":paths[start:start+20]}),"application/json")
        artifacts.extend(response.get("artifacts") or [])
    by_path={str(x.get("general",{}).get("path")):x for x in artifacts}
    for asset in assets:
        artifact=by_path.get(f'default/{asset["repository"]}/{asset["artifact_path"]}') or {}; issues=artifact.get("issues") or []
        behavior_issues=[x for x in issues if str(x.get("summary") or "").strip().lower() in {"suspicious skill","malicious skill"}]
        dependency_issues=[x for x in issues if x not in behavior_issues]
        summaries={str(x.get("summary") or "").strip().lower() for x in behavior_issues}
        if "malicious skill" in summaries: asset["security_status"]="Malicious"
        elif "suspicious skill" in summaries: asset["security_status"]="Suspicious"
        severity=Counter(str(x.get("severity") or "Unknown").lower() for x in dependency_issues)
        asset.update({"security_finding_ids":[x.get("issue_id") for x in behavior_issues if x.get("issue_id")],
                      "vulnerability_status":"Vulnerable" if dependency_issues else ("No known vulnerabilities" if artifact else "No Xray data"),
                      "vulnerability_count":len(dependency_issues),"critical_vulnerabilities":severity.get("critical",0),
                      "high_vulnerabilities":severity.get("high",0),"total_xray_findings":len(issues)})
    assets.sort(key=lambda x:(x["name"].lower(),x.get("repository") or ""))
    behavior=Counter(x["security_status"].lower().replace(" ","_") for x in assets)
    vulnerability=Counter(x["vulnerability_status"].lower().replace(" ","_") for x in assets); attribution=Counter(x["project_status"].lower() for x in assets)
    skills=evidence.setdefault("inventory",{}).setdefault("skills",{}); skills.update({"visible_assets":assets,"visible":len(assets),"total":len(assets)})
    skills["status"]="available"; skills.pop("reason",None)
    skills["scanned"]=sum(behavior.get(x,0) for x in ("not_malicious","malicious","suspicious"))
    skills["security_counts"]={x:behavior.get(x,0) for x in ("not_malicious","malicious","suspicious","scanning","not_scanned")}
    skills["vulnerability_counts"]={x:vulnerability.get(x,0) for x in ("vulnerable","no_known_vulnerabilities","no_xray_data")}
    skills["project_counts"]={x:attribution.get(x,0) for x in ("linked","unlinked","unknown")}
    evidence["security_collected_at"]=evidence["collected_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    evidence["status"]="available"
    evidence["collection_quality"]={"behavioral_status":"complete","dependency_xray_summaries":len(artifacts),
        "skills_total":len(assets),"repository_assignments":len(repository_projects),"visible_projects":len(visible_project_keys)}
    evidence["source"]="JFrog Skills status API, Xray artifact summary, Access Projects API and Artifactory repository configuration API"
    evidence["limitations"]=["Behavioral status and dependency vulnerability posture are separate; approved does not mean vulnerability-free.",
        "Project attribution proves the backing repository assignment. Additional read-only sharing to other projects is not inferred without project-scoped registry evidence.",
        "Current AI Catalog status is a dated revalidation and is not backdated to the report period."]
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(evidence,indent=2)+"\n"); print(args.output); return 0

if __name__=="__main__": raise SystemExit(main())
