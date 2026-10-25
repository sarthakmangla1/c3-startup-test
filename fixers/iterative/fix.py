#!/usr/bin/env python3
"""Evidence-driven iterative fixer for the C3 engineering take-home."""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
from collections import Counter
from pathlib import Path

WS = Path(os.environ.get("C3_WORKSPACE", os.getcwd())).resolve()
SRC = (WS / "src").resolve()
CORPUS = Path(os.environ["C3_CORPUS"]).resolve() if os.environ.get("C3_CORPUS") else None
DEADLINE = float(os.environ.get("C3_DEADLINE", time.time() + 840))
MODEL = os.environ.get("ANTHROPIC_MODEL", "anthropic/claude-sonnet-4.6")
SYSTEM = """You are a careful senior distributed-systems engineer repairing an unfamiliar service.
Use the incident ticket, trace/log evidence, source, public tests, invariants and C3 corpus to find
root causes, not just symptoms. Prefer the smallest correct general fix that works on unseen seeds.

Rules:
- Only files under src/ are graded. Never edit tests, simulator, scenarios, docs, grader or corpus.
- Do not special-case the public seed or hard-code outputs.
- Prefer platform/service documents marked CURRENT over SUPERSEDED documents.
- Consider loss, duplication, reordering, delays, restarts, pauses, clock drift, retries,
  idempotency, fencing, durability and terminal-state races where relevant.
- Revalidate lease validity immediately before every lease-protected send, including each retry
  after timeouts or backoff; never continue a retry loop after expiry.
- Keep capacity reserved until a GPU release is observably complete, not just requested/acknowledged.
- Maintain existing interfaces and compatibility with the codebase.
Return only complete replacement/new source files in this format:
=== FILE: src/relative/path.py ===
<complete new contents>
=== END ===
No markdown fences, shell commands, or files outside src/. Only include files that need edits."""
STOP = set("a about above after again against all also am an and any are as at be because been before being below between both but by can did do does doing down during each few for from further had has have having he her here hers herself him himself his how i if in into is it its itself just more most my myself no nor not of off on once only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves then there these they this those through to too under until up very was we were what when where which while who whom why will with would you your yours yourself yourselves".split())

def log(s): print(s, flush=True)
def remaining(): return DEADLINE - time.time()
def read(p, limit=None, tail=False):
    try: s=p.read_text(errors="replace")
    except OSError: return ""
    if limit and len(s)>limit: return ("[truncated head]\n"+s[-limit:]) if tail else s[:limit]+"\n[truncated]"
    return s
def run(argv, seconds, label):
    if seconds <= 0: return {"label":label,"returncode":None,"timeout":True,"output":"time limit"}
    env=os.environ.copy()
    old=[p for p in env.get("PYTHONPATH","").split(os.pathsep) if p]
    # Mirror the grader's clean import path: case root, service source, then simulator.
    parts=[str(WS), str(SRC), str(WS/"sim")]
    env["PYTHONPATH"]=os.pathsep.join(dict.fromkeys(parts+old))
    env["PYTHONHASHSEED"]="0"
    env["PYTHONDONTWRITEBYTECODE"]="1"
    try:
        p=subprocess.run(argv,cwd=WS,env=env,capture_output=True,text=True,timeout=max(1,seconds))
        out=(p.stdout or "")+("\n--- stderr ---\n"+p.stderr if p.stderr else "")
        return {"label":label,"returncode":p.returncode,"timeout":False,"output":out[-6000:]}
    except subprocess.TimeoutExpired as e:
        a=e.stdout or ""; b=e.stderr or ""
        if isinstance(a,bytes): a=a.decode(errors="replace")
        if isinstance(b,bytes): b=b.decode(errors="replace")
        return {"label":label,"returncode":None,"timeout":True,"output":(a+"\n"+b)[-4000:]}
    except Exception as e: return {"label":label,"returncode":None,"timeout":False,"output":f"{type(e).__name__}: {e}"}
def case_meta():
    try: return json.loads((WS/"case.json").read_text())
    except Exception: return {}
def checks(label,seeds):
    out=[]
    out.append(run([sys.executable,"-m","pytest","-q","tests"],min(90,max(2,remaining()-110)),label+": pytest"))
    for seed in seeds[:5]:
        if remaining()<22: break
        d=Path(tempfile.mkdtemp(prefix="c3-fixer-trace-"))
        r=run([sys.executable,"-m","sim","replay","--scenario","public","--seed",str(seed),"--out",str(d)],min(45,max(2,remaining()-22)),f"{label}: replay {seed}")
        out.append(r); trace=d/"trace.jsonl"
        if trace.is_file() and remaining()>10:
            out.append(run([sys.executable,"-m","sim","check","--trace",str(trace)],min(18,max(1,remaining()-8)),f"{label}: invariant check {seed}"))
        shutil.rmtree(d,ignore_errors=True)
    return out
def terms(s):
    words=re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{2,}",s.lower()); c=Counter(w for w in words if w not in STOP and not w.isdigit())
    for x in re.findall(r"[A-Za-z]+(?:_[A-Za-z0-9]+)+",s):
        x=x.lower(); c[x]+=4
        for z in x.split("_"):
            if len(z)>3 and z not in STOP: c[z]+=1
    return [x for x,_ in c.most_common(24)]
def corpus_context(seed):
    if not CORPUS or not CORPUS.is_dir(): return "[C3_CORPUS unavailable]"
    meta=case_meta(); roots=[CORPUS/"platform"]
    if meta.get("codebase"): roots.append(CORPUS/"service"/str(meta["codebase"]).upper())
    roots.append(CORPUS/"service")
    files=[]; seen=set()
    for root in roots:
        if root.is_dir():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".md",".txt",".rst",".yaml",".yml",".json"} and p not in seen:
                    files.append(p); seen.add(p)
    if not files:
        for p in CORPUS.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".md",".txt",".rst",".yaml",".yml",".json"}:
                files.append(p)
                if len(files)>1200: break
    ts=terms(seed); ranked=[]
    for p in files[:1600]:
        try:
            if p.stat().st_size>2_000_000: continue
            body=p.read_text(errors="replace")
        except OSError: continue
        low=body.lower(); rel=str(p.relative_to(CORPUS)); score=0
        for t in ts:
            n=low.count(t)
            if n: score+=min(n,8)*(2 if "_" in t or "." in t else 1)+(8 if t in rel.lower() else 0)
        if p.name in {"leases-and-fencing.md","idempotency.md","runtime-v3.md","changelog.md"}: score+=3
        if score: ranked.append((score,rel,body))
    ranked.sort(key=lambda x:(-x[0],x[1])); picked=[]; used=0
    for score,rel,body in ranked[:10]:
        lines=body.splitlines(); hits=[]
        for i,line in enumerate(lines):
            if any(t in line.lower() for t in ts[:14]): hits.append("\n".join(lines[max(0,i-1):min(len(lines),i+3)]))
        block=f"\n## {rel} (relevance {score})\n{body[:800]}\n"+"\nRelevant passages:\n"+"\n...\n".join(hits[:5]) if hits else f"\n## {rel}\n{body[:1600]}\n"
        block=block[:2400]
        if used+len(block)>14000: break
        picked.append(block); used+=len(block)
    index=read(CORPUS/"INDEX.md",4000) or read(CORPUS/"index.md",4000)
    return "# Corpus index\n"+index+"\n# Relevant corpus references\n"+("".join(picked) or "[no relevant lexical matches]")
def gather_case():
    sections=[]
    for name in ("SYMPTOM.md","README.md","INVARIANTS.md","scenario_schema.md","case.json"):
        v=read(WS/name,8000)
        if v: sections.append(f"\n=== {name} ===\n{v}\n")
    testroot=WS/"tests"
    if testroot.is_dir():
        for p in sorted(testroot.rglob("test_*.py"))[:18]:
            sections.append(f"\n=== {p.relative_to(WS)} ===\n{read(p,2600)}\n")
    logs=[]
    logroot=WS/"logs"
    if logroot.is_dir():
        for p in sorted(logroot.rglob("*.log")):
            logs.append(f"\n=== log {p.relative_to(WS)} (tail) ===\n{read(p,2800,True)}\n")
    return "# Ticket, invariants, tests and logs\n"+"".join(sections)+"\n# Log excerpts\n"+"".join(logs)[-10000:]
def gather_source():
    parts=[]; used=0
    for p in sorted(x for x in SRC.rglob("*") if x.is_file() and x.suffix.lower() in {".py",".toml",".yaml",".yml",".json",".ini",".cfg"} and "__pycache__" not in x.parts):
        block=f"\n=== {p.relative_to(WS)} ===\n{read(p,10000)}\n"
        if used+len(block)>58000:
            parts.append("[remaining source omitted at context limit]"); break
        parts.append(block); used+=len(block)
    return "".join(parts)
def diagnostics_text(ds):
    return "\n".join(f"\n## {x['label']} | exit={x['returncode']} | timeout={x['timeout']}\n{x['output']}" for x in ds)[:17000]
def log_check_failures(ds):
    """Expose actionable child-process errors in fixer.log, not just exit codes."""
    for d in ds:
        if d["timeout"] or d["returncode"] not in (0, None):
            output=(d.get("output") or "").strip()
            if output:
                log(f"CHECK DETAIL [{d['label']}]: {output[-1800:]}")
def model(prompt):
    base=os.environ.get("OPENAI_BASE_URL","").rstrip("/")
    key=os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not base or not key: log("Model endpoint/key missing; no patch attempted."); return ""
    if remaining()<35: log("Insufficient time for model call."); return ""
    body={"model":MODEL,"temperature":0.1,"max_tokens":8500,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}]}
    req=urllib.request.Request(base+"/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=max(10,min(360,int(remaining()-25)))) as res: obj=json.loads(res.read())
        return obj["choices"][0]["message"]["content"] or ""
    except urllib.error.HTTPError as e:
        log(f"Model HTTP {e.code}: {e.read(500).decode(errors='replace')}")
    except Exception as e: log(f"Model error {type(e).__name__}: {e}")
    return ""
def parse(reply):
    return re.findall(r"^=== FILE: (src/[^\r\n]+) ===\r?\n(.*?)\r?\n=== END ===",reply,re.M|re.S)
def target_for(rel):
    if not rel.startswith("src/"): return None
    p=(WS/rel).resolve()
    try: p.relative_to(SRC)
    except ValueError: return None
    if p==SRC or p.suffix.lower() not in {".py",".toml",".yaml",".yml",".json",".ini",".cfg"}: return None
    return p
def apply(reply):
    blocks=parse(reply)
    if not blocks: log("No parseable file markers returned."); log(reply[:800]); return 0
    count=0; seen=set()
    for rel,contents in blocks:
        p=target_for(rel.strip())
        if p is None or str(p) in seen: log(f"Rejecting unsafe/duplicate path: {rel}"); continue
        seen.add(str(p))
        if p.exists() and not p.is_file(): log(f"Not a file: {rel}"); continue
        p.parent.mkdir(parents=True,exist_ok=True); p.write_text(contents.rstrip("\n")+"\n"); log(f"Updated {rel}"); count+=1
    return count
def snapshot():
    return {str(p.relative_to(SRC)):p.read_bytes() for p in SRC.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
def restore(state):
    SRC.mkdir(parents=True,exist_ok=True)
    for p in SRC.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts and str(p.relative_to(SRC)) not in state: p.unlink()
    for rel,data in state.items():
        p=SRC/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
def prompt(case,source,docs,ds,feedback=""):
    return f"""Diagnose and fix the reported distributed-systems bug(s).

{case}

# Current source (all edits must be under src/)
{source}

# Retrieved C3 platform/service reference material
{docs}

# Baseline or latest validation results
{diagnostics_text(ds)}

# Feedback
{feedback or '[first attempt]'}

Inspect evidence carefully and do not assume the ticket's initial diagnosis is correct.
Choose the smallest coherent root-cause fix that respects source contracts. Public tests must
continue passing and relevant invariants should pass across seeds. Return only complete file blocks."""
def main():
    if not SRC.is_dir(): log(f"Missing source directory: {SRC}"); return 0
    log(f"Workspace={WS}; corpus={CORPUS}; remaining={remaining():.0f}s; budget="+os.environ.get("C3_BUDGET_USD","?"))
    meta=case_meta(); seeds=meta.get("public_seeds",[]) or [1]
    case=gather_case(); source=gather_source(); docs=corpus_context(case+"\n"+source[:18000])
    original=snapshot()
    base=checks("baseline",seeds)
    log("Baseline: "+"; ".join(f"{d['label']}={d['returncode']}" for d in base))
    log_check_failures(base)
    reply=model(prompt(case,source,docs,base))
    if not reply or not apply(reply): log("No patch applied."); return 0
    latest=checks("patched-1",seeds)
    test=next((d for d in latest if d["label"].endswith(": pytest")),None)
    test_ok=bool(test and test["returncode"]==0 and not test["timeout"])
    sim=[d for d in latest if ": invariant check " in d["label"]]
    sim_ok=bool(sim) and all(d["returncode"]==0 and not d["timeout"] for d in sim)
    log("Patched-1: "+"; ".join(f"{d['label']}={d['returncode']}" for d in latest))
    log_check_failures(latest)
    if remaining()>150 and (not test_ok or not sim_ok):
        prior=snapshot(); src2=gather_source()
        note="Inspect the latest applied patch and validation output; return only needed src files. "
        note+=("CRITICAL: public pytest failed; fix the regression first. " if not test_ok else "")
        note+=("Simulator invariant checks failed or were unavailable; improve the root-cause patch if supported by evidence." if not sim_ok else "")
        reply2=model(prompt(case,src2,docs,latest,note))
        if reply2 and apply(reply2):
            second=checks("patched-2",seeds); t2=next((d for d in second if d["label"].endswith(": pytest")),None)
            log("Patched-2: "+"; ".join(f"{d['label']}={d['returncode']}" for d in second))
            log_check_failures(second)
            if t2 and t2["returncode"]==0 and not t2["timeout"]:
                latest=second; log("Kept refinement: public pytest passes.")
            else:
                restore(prior); log("Discarded refinement because public pytest failed.")
    test=next((d for d in latest if d["label"].endswith(": pytest")),None)
    if not test or test["returncode"]!=0 or test["timeout"]:
        restore(original); log("Restored original src: public pytest did not pass.")
    else: log(f"Leaving patch in place; public pytest exit={test['returncode']}.")
    log("Done. Only source files below $C3_WORKSPACE/src were modified.")
    return 0
if __name__=="__main__": sys.exit(main())
