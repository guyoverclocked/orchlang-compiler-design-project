import sys, os, re, json
root = sys.argv[1]
pat_graph = re.compile(r'StateGraph\s*[(<]|MessageGraph\s*\(|add_conditional_edges|addConditionalEdges|Command\s*\(\s*goto|new Command\s*\(\s*\{\s*goto|goto\s*[:=]|\bSend\s*\(|new Send\s*\(|@entrypoint|entrypoint\s*\(')
pat_llm = re.compile(r'init_chat_model|initChatModel|Chat(OpenAI|Anthropic|Ollama|Cohere|MistralAI|Google|Groq|Fireworks|Bedrock|VertexAI)\b|with_structured_output|withStructuredOutput|bind_tools|bindTools|create_agent|createAgent|create_react_agent|createReactAgent|llm\.invoke|model\.invoke|llm\.ainvoke|model\.ainvoke')
exts = ('.md','.mdx','.ipynb','.py','.ts','.js')
rows=[]
for dp, dn, fn in os.walk(root):
    if 'node_modules' in dp or '/.git' in dp: continue
    for f in fn:
        if not f.endswith(exts): continue
        p=os.path.join(dp,f)
        try:
            if f.endswith('.ipynb'):
                nb=json.load(open(p))
                lines=[]
                for c in nb.get('cells',[]):
                    src=c.get('source',[])
                    if isinstance(src,str): src=src.splitlines(True)
                    lines.extend(src if c.get('cell_type')=='code' else [])
                text=''.join(lines)
            else:
                text=open(p,errors='ignore').read()
        except Exception as e:
            continue
        g=len(pat_graph.findall(text)); l=len(pat_llm.findall(text))
        sg=len(re.findall(r'StateGraph\s*[(<]',text)); ce=len(re.findall(r'add_conditional_edges|addConditionalEdges',text)); snd=len(re.findall(r'\bSend\s*\(',text)); cmd=len(re.findall(r'goto',text))
        if g: rows.append((os.path.relpath(p,root),sg,ce,snd,cmd,l))
for r in sorted(rows): print('\t'.join(map(str,r)))
