"""Independent JSON interpreter for the finite character-unit audit world.

This module imports neither the production core/compiler nor its runtime.
It is an executable reference, not a verified parser or deployment adapter.
"""


def expression(e, store):
    tag = e[0]
    if tag == "lit": return e[1]
    if tag == "var": return store.get(e[1], "")
    if tag == "app": return expression(e[1], store) + expression(e[2], store)
    if tag == "escape": return expression(e[1], store).replace("\\", "\\\\").replace(chr(31), "\\s")
    if tag == "trim": return expression(e[1],store).strip()
    raise ValueError("unknown expression")


def guard(g, store):
    value = store.get(g[1], "")
    return value == g[2] if g[0] == "eq" else value.startswith(g[2])


def shape(s):
    tag = s[0]
    if tag == "skip": return []
    if tag == "call": return None if s[6] is None else [["llm", s[3], *s[6]]]
    if tag in ("tool", "dummyTool"): return [["tool",s[2] if tag == "tool" else s[1]]]
    if tag == "dummy": return [["llm",*s[1:]]]
    if tag == "seq":
        a,b=shape(s[1]),shape(s[2])
        return None if a is None or b is None else a+b
    if tag == "ite":
        a,b=shape(s[2]),shape(s[3])
        return a if a is not None and a==b else None
    if tag == "loop":
        body=shape(s[3])
        return body*s[1] if s[4] and body is not None else None
    raise ValueError("unknown statement")


def execute(case):
    store=dict(case["store"])
    trace=[]
    rows={(m,r):v for m,r,v in case["kernels"]}
    if len(rows)!=len(case["kernels"]): raise ValueError("duplicate primitive key")

    def run(s):
        tag=s[0]
        if tag=="skip": return
        if tag=="seq": run(s[1]);run(s[2]);return
        if tag=="call":
            _,site,x,model,cap,request,pad=s
            req=expression(request,store)
            value=rows.get((model,req),"missing")[:cap]
            if pad is not None:
                if len(req)>pad[0]: raise ValueError("reference request exceeds target")
                inp,out=pad
            else: inp,out=len(req),len(value)
            store[x]=value
            trace.append(["llm",model,inp,out]);return
        if tag=="tool":
            _,x,name,arg=s
            value=expression(arg,store)
            # Generated differential cases use these three pure unary tools.
            if name=="upper":value=value.upper()[:6]
            elif name=="first":value=value[:1]
            elif name!="const":raise ValueError("unsupported reference tool")
            store[x]=value;trace.append(["tool",name]);return
        if tag=="dummy":trace.append(["llm",*s[1:]]);return
        if tag=="dummyTool":trace.append(["tool",s[1]]);return
        if tag=="ite":run(s[2] if guard(s[1],store) else s[3]);return
        if tag=="loop":
            _,bound,predicate,body,padded=s
            for index in range(bound):
                if guard(predicate,store):
                    if padded:
                        events=shape(body)
                        if events is None:raise ValueError("ghost body has no static shape")
                        trace.extend(events*(bound-index))
                    return
                run(body)
            return
        raise ValueError("unknown statement")

    run(case["program"])
    return dict(trace=trace,store=[[i,store.get(i,"")] for i in range(case["store_limit"])])
