import sys,re
pat_graph=re.compile(r'StateGraph\s*[(<]|@entrypoint|entrypoint\s*\(|MessageGraph\(')
pat_llm=re.compile(r'init_chat_model|initChatModel|Chat(OpenAI|Anthropic|Ollama|Cohere|MistralAI|Google\w*|Groq|Bedrock\w*|VertexAI|NVIDIA)\b|with_structured_output|withStructuredOutput|bind_tools|bindTools|create_agent|createAgent|create_react_agent|createReactAgent|(llm|model|agent|router|planner|evaluator|structured_llm|classifier)\w*\.(a?invoke|stream)\(')
for p in sys.argv[1:]:
    L=open(p,errors='ignore').read().split('\n')
    i=0
    while i<len(L):
        m=re.match(r'\s*```(\w+)?(.*)$',L[i])
        if m:
            lang=m.group(1) or ''; title=m.group(2).strip()
            j=i+1
            while j<len(L) and not re.match(r'\s*```\s*$',L[j]): j+=1
            body='\n'.join(L[i+1:j])
            if pat_graph.search(body):
                feats=[]
                if pat_llm.search(body): feats.append('LLM')
                for k,r in [('COND',r'add_conditional_edges|addConditionalEdges'),('SEND',r'\bSend\('),('GOTO',r'goto'),('INTERRUPT',r'interrupt\('),('WHILE',r'while '),('TOOLS',r'ToolNode|tools_condition|bind_tools|bindTools')]:
                    if re.search(r,body): feats.append(k)
                nodes=re.findall(r'add_?[nN]ode\(\s*["\']([^"\']+)',body)
                print(f'{p}:{i+1}-{j+1}\t{lang} {title}\t{",".join(feats)}\tnodes={nodes[:12]}')
            i=j+1
        else: i+=1
