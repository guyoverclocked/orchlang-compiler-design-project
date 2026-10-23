import sys, json, subprocess, urllib.parse, time
for q in sys.argv[1:]:
    url='https://api.crossref.org/works?rows=3&select=DOI,title,author,container-title,issued,event&query.bibliographic='+urllib.parse.quote(q)
    out=subprocess.run(['curl','-sS','-A','litsearch/1.0 (mailto:research@example.org)',url],capture_output=True,text=True).stdout
    print('==',q)
    try: items=json.loads(out)['message']['items']
    except Exception: print('ERR',out[:200]); continue
    for it in items:
        au=', '.join((a.get('given','')+' '+a.get('family','')).strip() for a in it.get('author',[])[:8])
        yr=it.get('issued',{}).get('date-parts',[[None]])[0][0]
        print('  ',yr,'|',(it.get('title') or [''])[0],'|',(it.get('container-title') or [''])[0],'|',it['DOI'],'|',au)
    time.sleep(0.5)
