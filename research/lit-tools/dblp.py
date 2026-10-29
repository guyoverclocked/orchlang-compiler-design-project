import sys, json, subprocess, urllib.parse, time
for q in sys.argv[1:]:
    url='https://dblp.org/search/publ/api?format=json&h=4&q='+urllib.parse.quote(q)
    out=''
    for i in range(3):
        out=subprocess.run(['curl','-sS',url],capture_output=True,text=True).stdout
        if out.strip().startswith('{'): break
        time.sleep(2)
    print('==',q)
    try:
        hits=json.loads(out)['result']['hits'].get('hit',[])
    except Exception as e:
        print('ERR',out[:200]); continue
    for h in hits:
        i=h['info']; a=i.get('authors',{}).get('author',[])
        if isinstance(a,dict): a=[a]
        print('  ',i.get('year'),'|',i.get('title'),'|',i.get('venue'),'|',i.get('pages',''),'|',i.get('doi',''),'|',', '.join(x['text'] for x in a[:8]))
    time.sleep(1)
