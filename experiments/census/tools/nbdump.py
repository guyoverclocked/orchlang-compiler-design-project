# Dump notebook cells with raw JSON file line numbers. Usage: nbdump.py file.ipynb [code|all]
import sys, json, re
p=sys.argv[1]; mode=sys.argv[2] if len(sys.argv)>2 else 'code'
lines=open(p,encoding='utf-8').read().split('\n')
ctype=None; insrc=False; cell=0
for i,l in enumerate(lines,1):
    s=l.strip()
    m=re.match(r'"cell_type":\s*"(\w+)"',s)
    if m: ctype=m.group(1); cell+=1; continue
    if not insrc and re.match(r'"source":\s*\[',s):
        insrc=True
        if s.endswith(']') or s.endswith('],'):
            insrc=False
        if mode=='all' or ctype=='code': print(f'----- cell {cell} [{ctype}]')
        continue
    if not insrc and re.match(r'"source":\s*"',s):
        if mode=='all' or ctype=='code':
            print(f'----- cell {cell} [{ctype}]'); 
            v=json.loads(s[len('"source":'):].strip().rstrip(','))
            for j,x in enumerate(v.split('\n')): print(f'{i:6d}| {x}')
        continue
    if insrc:
        if s in (']','],'):
            insrc=False; continue
        if mode=='all' or ctype=='code':
            try: v=json.loads(s.rstrip(',') if s.endswith('",') else s)
            except Exception: v=s
            print(f'{i:6d}| {v.rstrip(chr(10))}')
