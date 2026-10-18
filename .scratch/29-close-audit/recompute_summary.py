"""Read explicit final measurement roots; retain bounded projections and byte observations."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import runpy

HOME = Path(__file__).resolve().parent
BASE = Path('/tmp/wave1/final')
TARGETS = ['T-33', 'T-12', 'T-35', 'T-30', 'T-16', 'T-26', 'A-02', 'A-03', 'A-04', 'T-27', 'T-34']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, obj):
    (HOME/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')


# All root definitions are copied from, and checked against, retained analyze_n25.py.
inputs = {}
observations = []
totals = Counter()
for arm in ['ours', 'pi']:
    for seed in range(1, 26):
        if arm == 'ours':
            if seed <= 5:
                root=BASE/'our-n5'; runidx=seed
            elif seed <= 9:
                root=BASE/'n9/our-extra'; runidx=seed-5
            else:
                root=BASE/('n17' if seed<=17 else 'n25')/'our-extra'/f'seed{seed}'; runidx=1
            paths=[root/lane/'none/results.jsonl' for lane in ['lane1','lane2','lane3','lane4']]
        else:
            root=BASE/('n9' if seed<=9 else 'n17' if seed<=17 else 'n25')/('pi-n9' if seed<=9 else 'pi-extra')/f'seed{seed}'; runidx=1
            paths=[root/lane/'results.jsonl' for lane in ['lane1','lane2','lane3','lane4']]
        count=0
        for path in paths:
            data=path.read_bytes();inputs[str(path)]=sha(data)
            for line,text in enumerate(data.decode().splitlines(),1):
                r=json.loads(text)
                if arm=='ours' and r['run_idx']!=runidx:
                    continue
                count+=1;totals[arm+'-rows']+=1;totals[arm+'-pass']+=int(r['actual'])
                if not any(r['task'].startswith(t) for t in TARGETS):
                    continue
                observations.append(dict(arm=arm,seed=seed,task=r['task'],actual=r['actual'],claimed=r['claimed'],files_touched=r.get('files_touched'),timed_out=r.get('timed_out'),source=str(path),source_line=line,row_sha256=sha(text.encode())))
        assert count==40, (arm,seed,count)
assert len(observations)==550
save('outcomes-selected.json',observations)
save('summary-input-hashes.json',inputs)
print('N25 totals',dict(totals))
print('task ours-pass pi-pass pi-failed-no-files-touched (metadata, not byte proof)')
for t in TARGETS:
    ours=[r for r in observations if r['arm']=='ours' and r['task'].startswith(t)]
    pi=[r for r in observations if r['arm']=='pi' and r['task'].startswith(t)]
    print(t,sum(r['actual'] for r in ours),sum(r['actual'] for r in pi),sum(not r['actual'] and not r['files_touched'] for r in pi))
# Independent agreement with frozen producer, no bootstrap or model execution.
m=runpy.run_path(str(HOME/'evidence/analyze_n25.py'))
a,b=m['collect'](25)
assert sum(r['actual'] for r in a)==totals['ours-pass']==616
assert sum(r['actual'] for r in b)==totals['pi-pass']==624
print('frozen producer totals agree')

r3=[]
extra_manifest=[]
for arm in ['leaf','tree-greedy','tree-tournament']:
    for p in sorted((BASE/'r3'/arm).glob('*/run.json')):
        data=p.read_bytes();r=json.loads(data)
        original=Path('bench/corpus')/r['task']/'repo'
        files=[q for q in original.rglob('*.py') if 'tests' not in q.relative_to(original).parts and not q.name.startswith('test_')]
        assert files
        hashes=[]
        for q in files:
            final=p.parent/'work'/q.relative_to(original)
            hashes.append(dict(path=str(q.relative_to(original)),pristine_sha256=sha(q.read_bytes()),final_sha256=sha(final.read_bytes()) if final.is_file() else None))
        r3.append(dict(arm=arm,task=r['task'],actual=r['actual'],claimed=r['claimed'],unchanged_python=all(x['pristine_sha256']==x['final_sha256'] for x in hashes),source=str(p),source_sha256=sha(data),source_files=hashes))
        if p.parent.name=='T-02-off-by-one-1':
            target=HOME/'evidence'/f'r3-{arm}-T-02-s1'/'run.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            extra_manifest.append(dict(source=str(p),target=str(target.relative_to(HOME)),sha256=sha(data),bytes=len(data),mode='byte-copy'))
            for q in files:
                f=p.parent/'work'/q.relative_to(original);dest=target.parent/'work'/q.relative_to(original);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
                extra_manifest.append(dict(source=str(f),target=str(dest.relative_to(HOME)),sha256=sha(f.read_bytes()),bytes=f.stat().st_size,mode='byte-copy'))
for arm in ['leaf','tree-greedy','tree-tournament']:
    rs=[r for r in r3 if r['arm']==arm];assert len(rs)==70
    print('R3',arm,dict(Counter((r['actual'],r['claimed']) for r in rs)),'failed-unchanged',sum(not r['actual'] and r['unchanged_python'] for r in rs))
save('r3-observations.json',r3)
save('manifest-supplement.json',extra_manifest)
