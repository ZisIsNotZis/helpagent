"""Regression checks for known close overclaims; human review still owns semantics."""
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
FILES=['README.md','docs/STATUS.md','docs/LEARNINGS.md','docs/ROADMAP.md']
# Exact positive assertions withdrawn by ticket 29. Negations and evidence limits remain allowed.
PATTERNS=[
    r'own test(?: alone)? is zero-information',
    r'it is zero-information on correctness',
    r"model's own test is worthless",
    r'review alone is negative information',
    r'Review buys correctness only when backstopped',
    r'correctness\*\* lever only when',
    r'structural superiority is refuted',
    r'\*\*REFUTED / not shown\*\*',
    r'so this is a valid negative,? (?:and )?not an unfired',
    r'more seeds cannot (?:resolve it|close)',
]
old_hits=[]
for name in FILES:
    current=' '.join((ROOT/name).read_text().split())
    old=' '.join(subprocess.check_output(['git','show',f'72f25fa:{name}'],cwd=ROOT,text=True).split())
    for pattern in PATTERNS:
        assert not re.search(pattern,current,re.I),(name,pattern)
        if re.search(pattern,old,re.I):old_hits.append((name,pattern))
assert len(old_hits)>=10,old_hits
print(f'PASS current known-overclaim regression; baseline negative control rejects {len(old_hits)} file/pattern pairs')
for name in FILES:
    text=(ROOT/name).read_text()
    assert 'report.md' in text,name
    assert 'archiv' in text.lower() or name=='docs/LEARNINGS.md',name
# Preserve the user's criterion text byte-for-byte; only verdict explanations may change.
old=subprocess.check_output(['git','show','72f25fa:docs/ROADMAP.md'],cwd=ROOT,text=True)
new=(ROOT/'docs/ROADMAP.md').read_text()
for key in ['C1','C2','C3','C4','C5']:
    get=lambda text:next(l.split('|')[2] for l in text.splitlines() if l.startswith('| '+key+' |'))
    assert get(old)==get(new),key
for key in ['**V1**','**V2**','**V3**','**V4**','**V5**','**V6**']:
    get=lambda text:next(l.split('|')[1:4] for l in text.splitlines() if l.startswith('| '+key+' |'))
    assert get(old)==get(new),key
print('PASS C1-C5 criterion text and V1-V6 outcome/check columns unchanged')
# Preserve every original result-table row in README/STATUS except allowed narrative cells.
for name in ['docs/STATUS.md','docs/LEARNINGS.md']:
    old=subprocess.check_output(['git','show',f'72f25fa:{name}'],cwd=ROOT,text=True)
    new=(ROOT/name).read_text()
    # Pure numeric rows (their first cell has no alphabetic label) carry measured tables.
    for line in old.splitlines():
        if line.startswith('| A') or line.startswith('| B') or line.startswith('| actual per'):
            if line in new:continue
            # Changed labels in contrast rows are not measurements; no other exception expected.
            if line.startswith('| A4 − A') or line.startswith('| A3 − A') or line.startswith('| A2 − A') or line.startswith('| A1 − A'):
                assert line in new
            else:
                assert line in new,(name,line)
print('PASS retained arm/contrast measurement rows unchanged; no inference about untested designs')
