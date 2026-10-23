import sys, time, subprocess
import xml.etree.ElementTree as ET
ns={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}
ids=sys.argv[1]
full = len(sys.argv)>2
for attempt in range(4):
    out=subprocess.run(['curl','-sS',f'https://export.arxiv.org/api/query?id_list={ids}&max_results=50'],capture_output=True,text=True).stdout
    if out.strip():
        break
    time.sleep(3)
r=ET.fromstring(out)
for e in r.findall('a:entry',ns):
    g=lambda t: e.find(t,ns)
    c=g('x:comment'); j=g('x:journal_ref'); d=g('x:doi')
    print('ID:', g('a:id').text.split('/abs/')[-1])
    print('  T:', ' '.join(g('a:title').text.split()))
    print('  A:', ', '.join(a.find('a:name',ns).text for a in e.findall('a:author',ns)))
    print('  D:', g('a:published').text[:10], 'upd', g('a:updated').text[:10])
    if c is not None: print('  C:', ' '.join(c.text.split()))
    if j is not None: print('  J:', ' '.join(j.text.split()))
    if d is not None: print('  DOI:', d.text)
    if full: print('  S:', ' '.join(g('a:summary').text.split())[:1500])
