#!/usr/bin/env python3
"""M0 baseline runner — bare llm() whole-file-edit harness (DESIGN.md §8 M0, §4.7, §6).

Per corpus task (bench/corpus/T-*), up to MAX_ATTEMPTS attempts:
  1. copy the task dir into the run workdir (the corpus is never mutated),
  2. `checks.py snapshot` (baseline BEFORE any model write — bench/corpus/README.md),
  3. read request.md + every repo file; run pytest once to capture the failing output,
  4. ONE llm() call: POST /v1/chat/completions, temperature 0.2, max_tokens 3000,
     chat_template_kwargs {"enable_thinking": false}, response_format json_schema
     whole-file-edit envelope {status, comment, file_path, content},
  5. harness executes the envelope: write the file, run the task's pytest +
     `checks.py verify` (pytest gate + untouched-files contract),
  6. on red: roll back the written file; the next attempt's prompt carries a ONE-LINE
     harness failure summary + the failing test output (re-run on the rolled-back tree)
     + current file contents — NEVER the failed attempt's own text (erasure, §2.4).

Success per task = checks.py verify exit 0 (pytest green AND untouched-files contract OK).

Stdlib only. Owns exactly: bench/run_m0.py and bench/runs/.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "bench" / "corpus"
RUNS_DIR = ROOT / "bench" / "runs"

BASE_URL = os.environ.get("HELPAGENT_LLAMA_URL", "http://127.0.0.1:8833")
LLAMA_MODEL_PATH = (
    "/home/z/hf/models--XHToken--Spark-X2.5-4B-GGUF/snapshots/"
    "d313463f1ff7dc29db20193fddc4ad8386d16261/Spark-X2.5-4B-Q4_K_M.gguf"
)
MODEL_NAME = "spark-x2.5-4b"
TEMPERATURE = 0.2
MAX_TOKENS = 3000
MAX_ATTEMPTS = 3
HTTP_TIMEOUT_S = 600.0
HTTP_TRIES = 3
CMD_TIMEOUT_S = 300.0
PYTEST_TAIL_LINES = 40
PYTEST_TAIL_CHARS = 3000

ENVELOPE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "unable"]},
        "comment": {"type": "string"},
        "file_path": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["status", "comment", "file_path", "content"],
}

SYSTEM_PROMPT = """You are a precise whole-file coding-edit engine working on a small Python repository.

You receive: a bug report, the complete current contents of every file in the repository, and the failing test output. You return exactly ONE JSON object:

{"status": "ok" or "unable", "comment": "1-2 sentences: what the bug is and what you changed (or why you cannot fix it)", "file_path": "path of the ONE file you rewrite, exactly as shown in the repository listing", "content": "the COMPLETE new content of that file"}

Hard rules:
- "content" REPLACES the whole file byte-for-byte. Include every line of the file: module docstring, imports, and all. Never truncate, never write "..." or placeholders, never wrap the content in markdown fences.
- Change as little as possible: fix the reported bug and keep everything else exactly as it is. Do not restyle, rename, or reformat unrelated code.
- Do not change the public API: keep function and class names, signatures, and module layout unchanged.
- "file_path" must exactly match one of the repository file paths shown to you (relative to the repo root).
- If you are not confident you can fix the bug, set "status" to "unable", explain in "comment", and make "file_path" and "content" empty strings.
Output raw JSON only."""


# --------------------------------------------------------------------------- infra

def server_healthy() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL + "/health", timeout=5) as r:
            return json.loads(r.read().decode("utf-8")).get("status") == "ok"
    except Exception:
        return False


def ensure_server() -> None:
    if server_healthy():
        print(f"[server] healthy at {BASE_URL}")
        return
    print(f"[server] down; starting llama-server on {BASE_URL} ...")
    log = open("/tmp/llamasrv.log", "ab")
    subprocess.Popen(
        ["llama-server", "-m", LLAMA_MODEL_PATH, "--port", BASE_URL.rsplit(":", 1)[1],
         "-c", "8192", "-ngl", "99", "--host", "127.0.0.1"],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    deadline = time.time() + 180
    while time.time() < deadline:
        if server_healthy():
            print("[server] healthy")
            return
        time.sleep(2)
    raise RuntimeError("llama-server did not become healthy")


def run_cmd(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           timeout=CMD_TIMEOUT_S)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        return 124, f"TIMEOUT after {CMD_TIMEOUT_S}s\n{e.stdout or ''}\n{e.stderr or ''}"


def cap_tail(text: str, max_lines: int = PYTEST_TAIL_LINES,
             max_chars: int = PYTEST_TAIL_CHARS) -> str:
    lines = text.rstrip().splitlines()
    out = "\n".join(lines[-max_lines:])
    if len(out) > max_chars:
        out = out[-max_chars:]
    return out + "\n"


def pytest_summary_line(output: str) -> str:
    m = [ln for ln in output.splitlines()
         if re.search(r"\b\d+ (?:failed|passed|error)", ln)]
    return m[-1].strip() if m else "no summary line"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------- llm()

def build_body(messages: list[dict]) -> dict:
    return {
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "whole_file_edit",
                "strict": True,
                "schema": ENVELOPE_SCHEMA,
            },
        },
        "messages": messages,
    }


def llm(body: dict) -> tuple[dict | None, float, list[str]]:
    """POST /v1/chat/completions. Returns (response|None, model_wall_s, anomalies)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    anomalies: list[str] = []
    total_wall = 0.0
    for try_i in range(HTTP_TRIES):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
                payload = json.loads(r.read().decode("utf-8"))
            total_wall += time.perf_counter() - t0
            return payload, total_wall, anomalies
        except urllib.error.HTTPError as e:
            total_wall += time.perf_counter() - t0
            err_body = e.read().decode("utf-8", "replace")[:500]
            anomalies.append(f"http_{e.code}:{err_body}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            total_wall += time.perf_counter() - t0
            anomalies.append(f"transport_error:{type(e).__name__}:{e}")
        if try_i + 1 < HTTP_TRIES:
            time.sleep(2.0)
    return None, total_wall, anomalies


# --------------------------------------------------------------------------- prompt

def build_user_prompt(request_text: str, repo_files: dict[str, str],
                      failing_tests: str, retry_note: str | None) -> str:
    parts = ["## Bug report (verbatim, from the user)", request_text.strip(), ""]
    parts.append("## Repository files (complete current contents)")
    for rel in sorted(repo_files):
        fence = "```python" if rel.endswith(".py") else "```"
        parts += [f"### {rel}", fence, repo_files[rel], "```", ""]
    parts += [
        "## Failing test output (`python -m pytest` run inside the repository)",
        "```",
        failing_tests,
        "```",
        "",
    ]
    if retry_note:
        parts += [retry_note, ""]
    parts.append("Fix the bug by rewriting exactly one repository file. Respond with the JSON object now.")
    return "\n".join(parts)


def retry_failure_note(attempt: int, failure_reason: str, failing_tests: str) -> str:
    """ONE-LINE harness failure summary + current failing test output.

    Contains NONE of the failed attempt's own text (erasure semantics, DESIGN §2.4a).
    """
    return (
        "## Previous attempt failed\n"
        f"Attempt {attempt} of this task failed: {failure_reason} The repository still "
        "fails its tests; the file contents shown above are the current contents. Do not "
        "assume that attempt's approach was correct.\n"
        "\n"
        "## Failing test output (current)\n"
        "```\n"
        f"{failing_tests}"
        "```"
    )


# --------------------------------------------------------------------------- envelope

def validate_envelope(resp: dict | None,
                      repo_files: dict[str, str]) -> tuple[dict | None, list[str], str]:
    """Returns (envelope|None, anomalies, red_reason). red_reason == '' when executable."""
    if resp is None:
        return None, ["http_error"], "the model call failed (transport/HTTP error)"
    choices = resp.get("choices") or []
    if not choices:
        return None, ["empty_choices"], "the model response had no choices"
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    finish = choices[0].get("finish_reason")
    anomalies: list[str] = []
    if finish == "length":
        anomalies.append("truncated_max_tokens")
    if not isinstance(content, str) or not content.strip():
        return None, anomalies + ["empty_content"], "the model returned empty content"
    try:
        env = json.loads(content)
    except json.JSONDecodeError as e:
        return None, anomalies + ["invalid_json"], f"the model output was not valid JSON ({e})"
    if not isinstance(env, dict):
        return None, anomalies + ["invalid_json"], "the model output was not a JSON object"
    missing = [k for k in ("status", "comment", "file_path", "content") if k not in env]
    if missing:
        reason = f"the envelope was missing fields {missing}"
        return None, anomalies + ["schema_violation_missing_fields"], reason
    if env["status"] not in ("ok", "unable"):
        anomalies.append("schema_violation_status")
        return env, anomalies, "the envelope status was neither 'ok' nor 'unable'"
    if env["status"] == "unable":
        return env, anomalies, "unable"
    fp = env["file_path"]
    if not isinstance(fp, str) or fp not in repo_files:
        anomalies.append("schema_violation_file_path")
        return env, anomalies, "file_path did not exactly match any repository file"
    if not isinstance(env["content"], str) or env["content"] == "":
        anomalies.append("schema_violation_empty_content")
        return env, anomalies, "content was empty for a status='ok' envelope"
    return env, anomalies, ""  # executable


# --------------------------------------------------------------------------- runner

def read_repo_files(repo: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for p in sorted(repo.rglob("*")):
        if p.is_file() and not p.is_symlink():
            files[p.relative_to(repo).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
    return files


class Ledger:
    COLS = ["task_id", "attempt", "model_calls", "prompt_tokens", "completion_tokens",
            "cached_tokens", "model_wall_s", "harness_wall_s", "finish_reason",
            "envelope_status", "file_path", "pytest_exit", "verify_exit", "contract_ok",
            "outcome", "anomalies"]

    def __init__(self, path: Path):
        self._f = open(path, "w", newline="", encoding="utf-8")
        self._w = csv.writer(self._f)
        self._w.writerow(self.COLS)
        self._f.flush()

    def row(self, **kw) -> None:
        self._w.writerow([kw.get(c, "") for c in self.COLS])
        self._f.flush()


def append_jsonl(path: Path, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run_task(task_dir: Path, run_dir: Path, ledger: Ledger) -> dict:
    tid = task_dir.name
    print(f"\n=== {tid} ===")
    tdir = run_dir / "tasks" / tid
    task_copy = tdir / "work" / tid
    repo = task_copy / "repo"
    checks = task_copy / "checks.py"
    transcript = tdir / "transcript.jsonl"

    # -- setup (harness wall time; snapshot BEFORE any model write) ---------------
    t_setup0 = time.perf_counter()
    shutil.copytree(task_dir, task_copy,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache",
                                                  ".untouched.baseline.json"))
    snap_rc, snap_out = run_cmd([sys.executable, str(checks), "snapshot"], cwd=task_copy)
    assert snap_rc == 0, f"snapshot failed: {snap_out}"
    request_text = (task_dir / "request.md").read_text(encoding="utf-8")
    repo_files = read_repo_files(repo)
    base_rc, base_out = run_cmd([sys.executable, "-m", "pytest", "-q"], cwd=repo)
    assert base_rc != 0, f"{tid}: repo ships green?! corpus invariant violated"
    setup_wall = time.perf_counter() - t_setup0

    append_jsonl(transcript, {
        "type": "baseline", "task": tid, "pytest_exit": base_rc,
        "pytest_summary": pytest_summary_line(base_out), "pytest_output": base_out,
        "repo_files": sorted(repo_files),
        "request_sha256": sha256_bytes(request_text.encode("utf-8")),
        "snapshot": snap_out.strip(), "setup_harness_wall_s": round(setup_wall, 4),
    })
    (tdir / "baseline_pytest.txt").write_text(base_out, encoding="utf-8")
    print(f"[setup] snapshot ok; baseline pytest exit={base_rc} "
          f"({pytest_summary_line(base_out)}); setup_wall={setup_wall:.2f}s")

    failing_tests = cap_tail(base_out)
    stats = {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
             "cached_tokens": 0, "model_wall_s": 0.0, "harness_wall_s": 0.0,
             "unable_attempts": 0}
    task_anomalies: list[str] = []
    attempts_used = 0
    success = False
    outcome_per_attempt: list[dict] = []
    prev_retry_note: str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts_used = attempt
        t_att0 = time.perf_counter()

        # -- compose prompt + ONE llm() call ------------------------------------
        retry_note = prev_retry_note if attempt > 1 else None
        user_prompt = build_user_prompt(request_text, repo_files, failing_tests, retry_note)
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}]
        body = build_body(messages)
        att_dir = tdir / f"attempt-{attempt}"
        att_dir.mkdir(parents=True, exist_ok=True)
        (att_dir / "request_payload.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")

        resp, model_wall, anomalies = llm(body)
        (att_dir / "response.json").write_text(
            json.dumps(resp if resp is not None else {"transport_error": anomalies},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        usage = (resp or {}).get("usage") or {}
        p_tok = usage.get("prompt_tokens", 0)
        c_tok = usage.get("completion_tokens", 0)
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        finish = ((resp or {}).get("choices") or [{}])[0].get("finish_reason", "")
        stats["model_calls"] += 1
        stats["prompt_tokens"] += p_tok
        stats["completion_tokens"] += c_tok
        stats["cached_tokens"] += cached

        env, val_anoms, red_reason = validate_envelope(resp, repo_files)
        anomalies += val_anoms
        task_anomalies += anomalies

        # -- execute envelope + deterministic checks -----------------------------
        pytest_rc = verify_rc = None
        contract_ok = None
        wrote_fp, rolled_back = "", False
        wrote_red = False
        if red_reason == "":
            fp = env["file_path"]
            target = repo / fp
            original = target.read_bytes()
            target.write_text(env["content"], encoding="utf-8", newline="")
            wrote_fp = fp
            pytest_rc, pytest_out = run_cmd([sys.executable, "-m", "pytest", "-q"], cwd=repo)
            verify_rc, verify_out = run_cmd([sys.executable, str(checks), "verify"],
                                            cwd=task_copy)
            m = re.search(r"\[contract\]\s+(OK|FAIL)", verify_out)
            contract_ok = (m.group(1) == "OK") if m else False
            checks_txt = (
                f"== envelope application ==\nstatus=ok file_path={fp} "
                f"bytes={len(env['content'].encode('utf-8'))} "
                f"sha256={sha256_bytes(env['content'].encode('utf-8'))}\n\n"
                f"== pytest (after write, exit={pytest_rc}) ==\n{pytest_out}\n"
                f"== checks.py verify (exit={verify_rc}) ==\n{verify_out}\n"
            )
            if verify_rc == 0:
                success = True
            else:
                target.write_bytes(original)  # rollback before any retry
                rolled_back = True
                wrote_red = True
                checks_txt += "== rollback ==\nfile restored to original bytes\n"
        else:
            if env is not None and env.get("status") == "unable":
                stats["unable_attempts"] += 1
            pytest_rc, pytest_out = run_cmd([sys.executable, "-m", "pytest", "-q"], cwd=repo)
            verify_rc, verify_out = run_cmd([sys.executable, str(checks), "verify"],
                                            cwd=task_copy)
            m = re.search(r"\[contract\]\s+(OK|FAIL)", verify_out)
            contract_ok = (m.group(1) == "OK") if m else False
            checks_txt = (
                f"== envelope application ==\nNOT EXECUTED: {red_reason}\n\n"
                f"== pytest (exit={pytest_rc}) ==\n{pytest_out}\n"
                f"== checks.py verify (exit={verify_rc}) ==\n{verify_out}\n"
            )
        (att_dir / "checks.txt").write_text(checks_txt, encoding="utf-8")

        att_wall = time.perf_counter() - t_att0
        att_harness = att_wall - model_wall
        stats["model_wall_s"] += model_wall
        stats["harness_wall_s"] += att_harness
        outcome = "pass" if success else "fail"
        outcome_per_attempt.append({
            "attempt": attempt, "outcome": outcome,
            "envelope_status": (env or {}).get("status", ""), "file_path": wrote_fp,
            "pytest_exit": pytest_rc, "verify_exit": verify_rc, "anomalies": anomalies,
        })
        ledger.row(task_id=tid, attempt=attempt, model_calls=1, prompt_tokens=p_tok,
                   completion_tokens=c_tok, cached_tokens=cached,
                   model_wall_s=round(model_wall, 3), harness_wall_s=round(att_harness, 3),
                   finish_reason=finish, envelope_status=(env or {}).get("status", ""),
                   file_path=wrote_fp, pytest_exit=pytest_rc, verify_exit=verify_rc,
                   contract_ok=contract_ok, outcome=outcome,
                   anomalies=";".join(anomalies))
        append_jsonl(transcript, {
            "type": "attempt", "task": tid, "attempt": attempt, "outcome": outcome,
            "model_calls": 1, "prompt_tokens": p_tok, "completion_tokens": c_tok,
            "cached_tokens": cached, "model_wall_s": round(model_wall, 4),
            "attempt_wall_s": round(att_wall, 4), "finish_reason": finish,
            "envelope": None if env is None else {
                "status": env.get("status"), "comment": env.get("comment"),
                "file_path": env.get("file_path"),
                "content_sha256": sha256_bytes(str(env.get("content", "")).encode("utf-8")),
                "content_bytes": len(str(env.get("content", "")).encode("utf-8")),
                "content": env.get("content"),
            },
            "file_written": wrote_fp, "rolled_back": rolled_back,
            "pytest_exit": pytest_rc, "verify_exit": verify_rc, "contract_ok": contract_ok,
            "anomalies": anomalies, "red_reason": red_reason,
        })
        print(f"[attempt {attempt}] outcome={outcome} "
              f"env_status={(env or {}).get('status', '')!r} file={wrote_fp or '-'} "
              f"pytest={pytest_rc} verify={verify_rc} tokens={p_tok}+{c_tok} "
              f"model_wall={model_wall:.2f}s anomalies={anomalies or '-'}")

        if success:
            break

        # -- erasure-ready retry state: ground truth from the CURRENT tree --------
        if rolled_back:
            _, rb_out = run_cmd([sys.executable, "-m", "pytest", "-q"], cwd=repo)
            failing_tests = cap_tail(rb_out)
        else:
            failing_tests = cap_tail(pytest_out)
        repo_files = read_repo_files(repo)
        if wrote_red:
            failure_reason = ("the proposed whole-file edit was applied, but the test "
                              f"suite still failed ({pytest_summary_line(pytest_out)}).")
        elif red_reason == "unable":
            failure_reason = "no edit was applied because the proposed envelope reported status 'unable'."
        else:
            failure_reason = f"no edit was applied because the envelope was unusable: {red_reason}"
        prev_retry_note = retry_failure_note(attempt, failure_reason, failing_tests)

    return {
        "task": tid, "pass": success, "attempts_used": attempts_used,
        "model_calls": stats["model_calls"],
        "prompt_tokens": stats["prompt_tokens"],
        "completion_tokens": stats["completion_tokens"],
        "cached_tokens": stats["cached_tokens"],
        "model_wall_s": round(stats["model_wall_s"], 3),
        "harness_wall_s": round(setup_wall + stats["harness_wall_s"], 3),
        "wall_s": round(setup_wall + stats["model_wall_s"] + stats["harness_wall_s"], 3),
        "unable_attempts": stats["unable_attempts"],
        "anomalies": task_anomalies,
        "outcome_per_attempt": outcome_per_attempt,
    }


def main() -> int:
    t0 = time.perf_counter()
    ensure_server()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_DIR / ts
    i = 1
    while run_dir.exists():
        run_dir = RUNS_DIR / f"{ts}-{i}"
        i += 1
    (run_dir / "tasks").mkdir(parents=True)
    ledger = Ledger(run_dir / "ledger.csv")

    tasks = sorted(p for p in CORPUS_DIR.iterdir() if p.is_dir() and p.name.startswith("T-"))
    print(f"[run] {len(tasks)} tasks -> {run_dir}")

    results = [run_task(t, run_dir, ledger) for t in tasks]

    fixed = sum(1 for r in results if r["pass"])
    total_calls = sum(r["model_calls"] for r in results)
    total_ptok = sum(r["prompt_tokens"] for r in results)
    total_ctok = sum(r["completion_tokens"] for r in results)
    total_model_wall = sum(r["model_wall_s"] for r in results)
    total_harness_wall = sum(r["harness_wall_s"] for r in results)
    anomaly_counts: dict[str, int] = {}
    for r in results:
        for a in r["anomalies"]:
            key = a.split(":", 1)[0]
            anomaly_counts[key] = anomaly_counts.get(key, 0) + 1
    summary = {
        "run_id": run_dir.name,
        "utc": datetime.now(timezone.utc).isoformat(),
        "milestone": "M0 — bare llm() whole-file-edit baseline",
        "base_url": BASE_URL,
        "model": MODEL_NAME,
        "params": {
            "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": "json_schema whole-file-edit envelope",
            "max_attempts": MAX_ATTEMPTS,
        },
        "tasks_fixed": f"{fixed}/{len(results)}",
        "totals": {
            "model_calls": total_calls,
            "prompt_tokens": total_ptok,
            "completion_tokens": total_ctok,
            "total_tokens": total_ptok + total_ctok,
            "model_wall_s": round(total_model_wall, 3),
            "harness_wall_s": round(total_harness_wall, 3),
            "wall_s": round(total_model_wall + total_harness_wall, 3),
            "run_wall_s": round(time.perf_counter() - t0, 3),
        },
        "anomaly_counts": anomaly_counts,
        "tasks": results,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n=== RUN SUMMARY ({run_dir.name}) ===")
    for r in results:
        print(f"{r['task']:<28} attempts={r['attempts_used']} calls={r['model_calls']} "
              f"tok={r['prompt_tokens']}+{r['completion_tokens']} "
              f"wall={r['wall_s']:.2f}s (model {r['model_wall_s']:.2f} / harness "
              f"{r['harness_wall_s']:.2f})  {'PASS' if r['pass'] else 'FAIL'}")
    print(f"fixed {fixed}/{len(results)} | calls={total_calls} "
          f"tokens={total_ptok}+{total_ctok} | model_wall={total_model_wall:.2f}s "
          f"harness_wall={total_harness_wall:.2f}s | anomalies={anomaly_counts or '-'}")
    return 0 if fixed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
