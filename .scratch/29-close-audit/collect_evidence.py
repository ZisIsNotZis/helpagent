"""Bounded, read-only raw selection; only writes under this ticket. No grader/model calls."""
from pathlib import Path
import hashlib
import json

HOME = Path(__file__).resolve().parent
BASE = Path('/tmp/wave1/final')
PIN = '45ebb32f1be0977b9149057da3a80ee93ce22840'
manifest = []


def digest(data):
    return hashlib.sha256(data).hexdigest()


def copy(source, target):
    data = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    manifest.append(dict(source=str(source), target=str(target.relative_to(HOME)), sha256=digest(data), bytes=len(data), mode='byte-copy'))


def derived(source, target, data, **extra):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    manifest.append(dict(source=str(source), source_sha256=digest(source.read_bytes()), target=str(target.relative_to(HOME)), sha256=digest(data), bytes=len(data), mode='selection', **extra))


def dump(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()


# Explicit final seed-1/2 roots; inspect four lane result files, never the whole tree.
our_rows = []
pi_rows = []
for seed in [1, 2]:
    for lane in ['lane1', 'lane2', 'lane3', 'lane4']:
        for arm, path, out in [
            ('ours', BASE/'our-n5'/lane/'none/results.jsonl', our_rows),
            ('pi', BASE/'n9/pi-n9'/f'seed{seed}'/lane/'results.jsonl', pi_rows),
        ]:
            for line, raw in enumerate(path.read_text().splitlines(), 1):
                r = json.loads(raw)
                if arm == 'ours' and r['run_idx'] != seed:
                    continue
                out.append((seed, path, line, raw, r))

selected = []
for task, seed in [('T-33', 1), ('T-12', 1), ('T-35', 1), ('T-30', 2), ('T-16', 2), ('T-26', 1), ('A-02', 1), ('A-03', 1), ('A-04', 1), ('T-27', 1), ('T-34', 1)]:
    for arm, rows in [('ours', our_rows), ('pi', pi_rows)]:
        item = next(x for x in rows if x[0] == seed and x[4]['task'].startswith(task))
        selected.append((arm, *item))
# T26 pi#2 is a success control, selected from seed1..2, not by later outcome search.
item = next(x for x in pi_rows if x[0] == 2 and x[4]['task'].startswith('T-26'))
if item[4]['actual']:
    selected.append(('pi', *item))
else:
    # Explicitly bounded additional seed roots, stop at first observed success.
    for seed in range(3, 26):
        roots = ([BASE/'n9/pi-n9'/f'seed{seed}'] if seed <= 9 else
                 [BASE/('n17' if seed <= 17 else 'n25')/'pi-extra'/f'seed{seed}'])
        found = None
        for root in roots:
            for lane in ['lane1', 'lane2', 'lane3', 'lane4']:
                p = root/lane/'results.jsonl'
                for line, raw in enumerate(p.read_text().splitlines(), 1):
                    r = json.loads(raw)
                    if r['task'].startswith('T-26') and r['actual']:
                        found = ('pi', seed, p, line, raw, r)
        if found:
            selected.append(found)
            break
r2path = BASE/'r2/runs/c4/full/full/results.jsonl'
for line, raw in enumerate(r2path.read_text().splitlines(), 1):
    r = json.loads(raw)
    if r['task'] == 'A-05-zebra-puzzle' and r['run_idx'] == 1:
        selected.append(('r2-full', 1, r2path, line, raw, r))

samples = []
for arm, seed, path, line, raw, r in selected:
    sample = f'{arm}-{r["task"]}-s{seed}'
    out = HOME/'evidence'/sample
    run = path.parent/f'{r["task"]}-{r.get("run_idx", 1)}'
    derived(path, out/'row.json', (raw+'\n').encode(), source_line=line)
    files = []
    for filename in ['trajectory.jsonl', 'prompt.txt', 'rec.json']:
        if (run/filename).is_file():
            copy(run/filename, out/filename)
            files.append(filename)
    if (run/'events.jsonl').is_file():
        source = run/'events.jsonl'
        messages = []
        for n, text in enumerate(source.read_text().splitlines(), 1):
            event = json.loads(text)
            if event.get('type') in ['message_end', 'tool_execution_start', 'tool_execution_end']:
                messages.append(dict(source_line=n, event=event))
        derived(source, out/'events-selected.jsonl', ''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in messages).encode(), selection='message_end/tool_execution_start/tool_execution_end; omit streaming deltas')
        files.append('events-selected.jsonl')
    # Only bounded text artifacts; no caches, environments, binary files, or full grade repo.
    for folder in ['work', 'grade']:
        base = run/folder
        if not base.is_dir():
            continue
        for p in sorted(base.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or '.pytest_cache' in p.parts or '.venv' in p.parts:
                continue
            if p.suffix not in ['.py', '.txt', '.md', '.json', '.toml']:
                continue
            if folder == 'grade':
                # The actual consumed bytes after frozen-file restoration, not work alone.
                grade_repo = base/r['task']/'repo'
                if not p.is_relative_to(grade_repo):
                    continue
                copy(p, out/'grade-repo'/p.relative_to(grade_repo))
            else:
                copy(p, out/folder/p.relative_to(base))
    samples.append(dict(id=sample, arm=arm, seed=seed, task=r['task'], actual=r['actual'], claimed=r['claimed'], source_results=str(path), source_line=line, source_run=str(run), revision=PIN, artifacts=files))
    taskbase = Path('bench/anchor' if r['task'].startswith('A-') else 'bench/corpus')/r['task']
    if not taskbase.exists():
        taskbase = Path('bench/corpus')/r['task']
    # Retain exact visible specification and pristine source (the measurement code is unchanged).
    for p in [taskbase/'request.md', *sorted((taskbase/'repo').rglob('*.py')), *sorted((taskbase/'repo').rglob('README.md'))]:
        if p.is_file() and '__pycache__' not in p.parts:
            target = HOME/'evidence/specs'/r['task']/p.relative_to(taskbase)
            if not target.exists():
                copy(p, target)

copy(BASE/'n25/analyze_n25.py', HOME/'evidence/analyze_n25.py')
copy(Path('/home/z/.pi/agent/sessions/--home-z-vibe-helpagent--/subagent-artifacts/outputs/c84a86f9-2258-4314-a36c-2cffacc38905/.scratch/29-close-audit/investigation.md'), HOME/'evidence/prior-investigation.md')
(HOME/'samples.json').write_bytes(dump(samples))
(HOME/'manifest.json').write_bytes(dump(manifest))
print(f'{len(samples)} samples; {len(manifest)} retained files; {sum(x["bytes"] for x in manifest)} bytes')
for s in samples:
    print(s['id'], s['actual'], s['source_results']+':'+str(s['source_line']))
