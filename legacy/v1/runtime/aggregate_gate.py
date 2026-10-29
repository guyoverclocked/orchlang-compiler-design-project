"""Trusted source boundary for the separate aggregate-only two-call judgment.

Only one secret branch with exactly two closed literal-request calls in each
arm is supported. No response-dependent requests, public inputs, nested branches,
retry, tools, or nonliteral/branch outputs. The returned guarantee concerns an
account observer of per-contract usage totals, not C++ content confidentiality.
"""
from .finite_reference import Unsupported
from .source_gate import Reader, lex, sha


def actions(program):
    if (not isinstance(program,list) or len(program)!=4 or program[0]!='branch'):
        raise Unsupported('aggregate judgment needs exactly one secret branch')
    arms=[]
    for arm in program[2:]:
        if not isinstance(arm,list) or len(arm)!=3 or arm[0]!='seq':
            raise Unsupported('aggregate judgment needs exactly two calls per arm')
        for call in arm[1:]:
            if not isinstance(call,list) or len(call)!=3 or call[0]!='call' or not all(isinstance(v,str) for v in call[1:]):
                raise Unsupported('aggregate judgment requires independent closed calls')
        arms.append(arm[1:])
    return arms


def accepts(program):
    left,right=actions(program)
    return left==right or left==list(reversed(right))


def read_source(data):
    if len(data)>1_000_000:
        raise Unsupported('source byte limit')
    source=data.decode('utf-8',errors='strict')
    # Reader historically erases all literal outputs. This narrower interface
    # requires root outputs so a source-level output channel is not hidden.
    depth=0
    for token in lex(source):
        if token=='{':
            depth+=1
        elif token=='}':
            depth-=1
        elif token=='output' and depth!=1:
            raise Unsupported('aggregate judgment permits literal outputs only at workflow root')
    result=Reader(source).read()
    actions(result['program'])
    result['source_sha256']=sha(data)
    return result
