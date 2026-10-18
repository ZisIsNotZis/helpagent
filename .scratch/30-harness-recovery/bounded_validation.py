"""Ticket30's single admitted scope: verify live binding, execute queued proof, release."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
RECORD = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
LEDGER = Path(__file__).resolve().parent / "job-lifecycle.json"
RESERVE = 16 * 1024**3
START = time.monotonic()


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(tmp, path)


def transition(state, note):
    ledger = json.loads(LEDGER.read_text())
    ledger["state"] = state
    ledger["events"].append({"at": timestamp(), "state": state, "note": note})
    atomic(LEDGER, ledger)


def membership(pid):
    return Path(f"/proc/{pid}/cgroup").read_text().strip()


GROUP = Path("/sys/fs/cgroup") / membership(os.getpid()).split("::", 1)[1].lstrip("/")
SELF = os.getpid()


def snapshot():
    attrs = {name: (GROUP / name).read_text().strip() for name in (
        "cgroup.controllers", "cgroup.events", "cgroup.procs", "cpu.max", "cpu.stat",
        "memory.max", "memory.current", "memory.events", "pids.max", "pids.current", "pids.events")}
    available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))) * 1024
    procs = {}
    for pid in attrs["cgroup.procs"].split():
        try:
            procs[pid] = {"cgroup": membership(pid), "stat": Path(f"/proc/{pid}/stat").read_text(),
                          "affinity": sorted(os.sched_getaffinity(int(pid)))}
        except FileNotFoundError:
            continue
    return {"at": timestamp(), "group": str(GROUP), "attributes": attrs,
            "hostAvailableBytes": available, "processes": procs}


def guard(sample):
    attrs = sample["attributes"]
    quota, period = map(int, attrs["cpu.max"].split())
    assert quota <= period, "CPU quota exceeds 1CPU"
    assert int(attrs["memory.max"]) <= 1024**3, "memory not aggregate-capped"
    assert int(attrs["pids.max"]) <= 64, "tasks not capped"
    assert {"cpu", "memory", "pids"} <= set(attrs["cgroup.controllers"].split())
    assert sample["hostAvailableBytes"] >= RESERVE, "host reserve breached"
    assert all(len(proc["affinity"]) == 1 and proc["cgroup"] == membership(SELF)
               for proc in sample["processes"].values()), "descendant binding/affinity differs"
    assert all(int(line.split()[1]) == 0 for line in attrs["memory.events"].splitlines()
               if line.split()[0] in ("oom", "oom_kill")), "cgroup OOM"
    assert time.monotonic() - START < 3000, "job deadline"


def sample_and_guard():
    sample = snapshot()
    with (RECORD / "resource-monitor.jsonl").open("a") as stream:
        stream.write(json.dumps(sample, sort_keys=True) + "\n")
    guard(sample)
    return sample


def extras():
    return {int(pid) for pid in (GROUP / "cgroup.procs").read_text().split()} - {SELF}


def stop_owned_payload():
    # Only this uniquely named scope's members; never a process-name match or other job.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in extras():
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(0.3)


def run(command):
    name = command["name"]
    sample_and_guard()
    files = ("harness/leaf.py", "tests/unit/test_own_test_setup.py", "tests/unit/test_v2_leaf.py")
    revision = {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest() for file in files}
    result = {"name": name, "argv": command["argv"], "expectedExit": command["expectedExit"],
              "startedAt": timestamp(), "sourceHashes": revision, "cgroup": str(GROUP)}
    transition("running-command", name)
    began = time.monotonic()
    with (RECORD / f"validation-{name}.txt").open("w") as output:
        child = subprocess.Popen(command["argv"], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        result["pid"] = child.pid
        while child.poll() is None:
            try:
                sample_and_guard()
                assert time.monotonic() - began < 599, "command deadline"
            except BaseException:
                stop_owned_payload()
                child.wait()
                raise
            time.sleep(0.5)
    result.update(exit=child.wait(), endedAt=timestamp(), elapsedSeconds=time.monotonic() - began)
    if extras():
        result["lingeringPayloadPids"] = sorted(extras())
        stop_owned_payload()
        result["cleanupRequired"] = True
    result["outputSha256"] = hashlib.sha256((RECORD / f"validation-{name}.txt").read_bytes()).hexdigest()
    atomic(RECORD / f"validation-{name}.json", result)
    transition("command-stopped", result)
    assert not extras(), "live descendants after payload"
    return result["exit"] == result["expectedExit"] and not result.get("cleanupRequired")


def main():
    transition("binding-probe", {"pid": SELF, "group": str(GROUP)})
    probe_code = ("import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-B','-c',"
                  "'import time; time.sleep(3)']); time.sleep(3); p.wait()")
    probe = subprocess.Popen([sys.executable, "-B", "-c", probe_code])
    time.sleep(0.5)
    proof = sample_and_guard()
    assert len(proof["processes"]) >= 3, "probe child/grandchild not live"
    atomic(RECORD / "runtime-binding.json", proof)
    probe.wait(timeout=8)
    assert not extras(), "probe descendants remain"
    transition("bound-awaiting-writer-verification", str(GROUP))
    while not (RECORD / "binding-approved").exists():
        sample_and_guard()
        time.sleep(0.5)
    transition("verified-admitted", "writer verified runtime-binding and systemd properties")
    consumed = 0
    while not (RECORD / "release-job").exists():
        queue = json.loads((RECORD / "validation-queue.json").read_text())
        if consumed < len(queue):
            command = queue[consumed]
            if not run(command):
                transition("proof-failed-awaiting-writer", command["name"])
                while not (RECORD / f"ack-{command['name']}").exists():
                    sample_and_guard()
                    time.sleep(0.5)
            consumed += 1
        else:
            sample_and_guard()
            time.sleep(0.5)
    final = sample_and_guard()
    assert not extras(), "payload descendants still live before release"
    atomic(RECORD / "descendants-stopped.json", final)
    transition("runner-exiting-awaiting-outside-stop-proof", {"pid": SELF, "payloadPids": []})


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        stop_owned_payload()
        transition("blocked-runtime-or-command", repr(exc))
        raise
