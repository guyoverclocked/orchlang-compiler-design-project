import sys, time, subprocess, urllib.parse
import xml.etree.ElementTree as ET
ns={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}
q=sys.argv[1]; n=sys.argv[2] if len(sys.argv)>2 else '8'
url='https://export.arxiv.org/api/query?search_query='+urllib.parse.quote(q)+f'&max_results={n}&sortBy=relevance'
for attempt in range(4):
    out=subprocess.run(['curl','-sS',url],capture_output=True,text=True).stdout
    if out.strip(): break
    time.sleep(3)
r=ET.fromstring(out)
for e in r.findall('a:entry',ns):
    g=lambda t: e.find(t,ns)
    print(g('a:id').text.split('/abs/')[-1], '|', g('a:published').text[:10], '|', ' '.join(g('a:title').text.split()), '|', ', '.join(a.find('a:name',ns).text for a in e.findall('a:author',ns)[:4]))
