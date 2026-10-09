#!/usr/bin/env python3
"""Authored small graph cases: this is a development corpus, not external ports."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def base():
    call=lambda result,argument='query': {'model':'m','template':'Process {value}',
        'arguments':[{'value':argument}], 'result':result}
    return {'format':'orchlang-request-graph','version':1,'name':'PrivateCyclicChain',
            'chars_per_token':4,
            'inputs':{'query':{'type':'text','label':'public','max_tokens':32},
                      'route':{'type':'boolean','label':'secret'}},
            'models':{'m':{'provider':'mock','model':'cycle-worker','max_tokens':16,'unit_price':0.001}},
            'registers':{'a':{'model':'m'},'b':{'model':'m'},'x':{'model':'m'},'y':{'model':'m'}},
            'entry':'choose',
            'states':{
                'choose':{'calls':[],'next':{'kind':'secret','guard':{'value':'route'},'then':'left','else':'right'}},
                'left':{'calls':[call('a'),call('b','a')],
                        'next':{'kind':'public','guard':{'value':'b','op':'<=','limit':8},'then':'choose','else':'stop'}},
                'right':{'calls':[call('x'),call('y','x')],
                         'next':{'kind':'public','guard':{'value':'y','op':'<=','limit':8},'then':'choose','else':'stop'}},
                'stop':{'calls':[],'next':{'kind':'stop'}}}}


def corpus():
    result=[]
    def put(group,name,graph,diagnostic=None):
        graph['name']=name;result.append((group,name,graph,diagnostic))
    g=base();put('accepted','matched_cyclic_chain',g)
    g=base();g['models']['alias']=copy.deepcopy(g['models']['m'])
    for c in g['states']['right']['calls']:c['model']='alias'
    put('accepted','canonical_alias_cycle',g)
    g=base();g['states']['right_second']={'calls':[g['states']['right']['calls'].pop()],
                                       'next':g['states']['right']['next']}
    g['states']['right']['next']={'kind':'goto','target':'right_second'}
    put('accepted','split_control_blocks',g)
    g=base();g['inputs']['inner']={'type':'boolean','label':'secret'}
    left=copy.deepcopy(g['states']['left']);g['states']['left_alt']=left
    g['states']['left']={'calls':[],'next':{'kind':'secret','guard':{'value':'inner'},'then':'left_body','else':'left_alt'}}
    g['states']['left_body']=left
    put('accepted','nested_private_choices',g)
    g=base()
    for s in ('left','right'):g['states'][s]['next']={'kind':'goto','target':'choose'}
    put('accepted','unbounded_productive_cycle',g)
    g=base()
    for s in ('left','right'):g['states'][s]['next']={'kind':'stop'}
    put('accepted','finite_private_chain',g)
    g=base();g['states']['right']['calls'][0]['template']='Different {value}'
    put('rejected','request_template_mutation',g,'templates differ')
    g=base();g['models']['other']={**g['models']['m'],'max_tokens':8}
    g['states']['right']['calls'][0]['model']='other'
    put('rejected','model_cap_mutation',g,'contracts differ')
    g=base();g['inputs']['query2']={'type':'text','label':'public','max_tokens':32}
    g['states']['right']['calls'][0]['arguments']=[{'value':'query2'}]
    put('rejected','different_public_input',g,'arguments')
    g=base();g['states']['right']['calls'].pop()
    g['states']['right']['next']={'kind':'stop'}
    put('rejected','private_termination_count',g,'events differ')
    g=base();g['states']['right']['next']['guard']['op']='<'
    put('rejected','unmatched_public_guard',g,'guards')
    g=base();g['states']['left']['calls']=[
        {'model':'m','template':'Process {value}','arguments':[{'value':'query'}],'result':'a'},
        {'model':'m','template':'Process {value}','arguments':[{'value':'query'}],'result':'a'},
        {'model':'m','template':'Process {value}','arguments':[{'value':'a'}],'result':'b'}]
    g['states']['right']['calls']=[
        {'model':'m','template':'Process {value}','arguments':[{'value':'query'}],'result':'x'},
        {'model':'m','template':'Process {value}','arguments':[{'value':'query'}],'result':'y'},
        {'model':'m','template':'Process {value}','arguments':[{'value':'x'}],'result':'y'}]
    put('rejected','overwritten_result_relation',g,'arguments')
    g=base();g['states']['right']['calls'][1]['arguments']=[{'literal':'fixed'}]
    put('rejected','literal_result_mutation',g,'arguments')
    g=base();g['states']['choose']['next']['else']='stop'
    put('rejected','one_sided_private_transition',g,'events differ')
    g=base();g['states']['empty_loop']={'calls':[],'next':{'kind':'goto','target':'empty_loop'}}
    g['states']['choose']['next']['then']='empty_loop'
    put('invalid','private_silent_cycle',g,'call-free cycle')
    g=base();g['states']['left']['calls'][0]['arguments']=[{'value':'route'}]
    put('invalid','secret_request_argument',g,'public text')
    g=base();g['models']['other']={**g['models']['m'],'model':'different-worker'}
    g['registers']['a']['model']='other'
    put('invalid','cross_token_unit',g,'token-unit')
    return result


def main():
    manifest=[]
    for group,name,graph,diagnostic in corpus():
        path=ROOT/'examples/graphs'/group/(name+'.json')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(graph,ensure_ascii=False,indent=2)+'\n')
        manifest.append({'path':str(path.relative_to(ROOT)),'expected':group,'diagnostic':diagnostic})
    (ROOT/'examples/graphs/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('wrote',len(manifest),'authored graph examples')

if __name__=='__main__':main()
