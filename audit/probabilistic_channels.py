#!/usr/bin/env python3
"""Exact finite success-only usage channels for a rational outcome-kernel model.

This is model-dependent, finite-horizon quantitative analysis. It does not
replace the graph checker's universal shared-oracle request theorem, validate
provider probabilities, or bound an infinite whole-execution bill. Kernels
condition on exact requests, ordinals, and an explicit finite complete-event
history window. All probabilities and histograms use Fraction arithmetic.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import sys

from orchgraph import Graph, InvalidGraph, natural, strict_json, utf8

KERNEL_FORMAT='orchlang-finite-outcome-kernel'
MAX_VALUE_BYTES=1024*1024
MAX_SOURCE_BYTES=16*1024*1024
MAX_CONTROL_STEPS=1000000
MAX_TRACE_BYTES=16*1024*1024
MAX_STATES=100000
MAX_HORIZON=32
MAX_WORK_BYTES=64*1024*1024
MAX_RATIONAL_BITS=8192
PROBABILITY=re.compile(r'^[1-9][0-9]{0,999}(?:/[1-9][0-9]{0,999})?$')


class ChannelError(ValueError):pass
class ChannelLimit(ChannelError):pass


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def sha(value):return hashlib.sha256(value).hexdigest()


def bounded_mass(value):
    if max(value.numerator.bit_length(),value.denominator.bit_length())>MAX_RATIONAL_BITS:
        raise ChannelLimit('exact rational arithmetic precision cap reached')
    return value


def exact_total(values):
    result=Fraction()
    for value in values:result=bounded_mass(result+value)
    return result


def bounded_document(value):
    """Validate JSON types before canonicalization can coerce object keys."""
    def visit(item,depth=0):
        if depth>256:raise ChannelError('JSON nesting limit reached')
        if isinstance(item,dict):
            if any(not isinstance(key,str)for key in item):raise ChannelError('JSON keys must be strings')
            for child in item.values():visit(child,depth+1)
        elif isinstance(item,list):
            for child in item:visit(child,depth+1)
        elif item is not None and type(item)not in (str,bool,int,float):
            raise ChannelError('non-JSON value')
    visit(value)
    encoded=utf8(canonical(value))
    if len(encoded)>MAX_SOURCE_BYTES:raise ChannelError('document byte cap reached')
    return strict_json(encoded)


def fields(value,required,optional=()):
    if not isinstance(value,dict):raise ChannelError('expected object')
    if set(value)-set(required)-set(optional) or set(required)-set(value):
        raise ChannelError('missing/unknown object fields')


def text(value):
    try:raw=utf8(value)
    except (InvalidGraph,TypeError) as error:raise ChannelError(str(error)) from error
    if len(raw)>MAX_VALUE_BYTES:raise ChannelLimit('kernel/request value exceeds byte limit')
    return value


def probability(value):
    if not isinstance(value,str) or not PROBABILITY.fullmatch(value):
        raise ChannelError('probability must be a bounded exact integer/fraction string')
    result=Fraction(value)
    if result<=0 or result>1:raise ChannelError('outcome probability must be in (0,1]')
    return result


def normalized_store(graph,store):
    if not isinstance(store,dict) or set(store)!=set(graph.inputs):raise ChannelError('store must contain exactly declared inputs')
    values={}
    for key,declaration in graph.inputs.items():
        value=store[key]
        if declaration['type']=='boolean':
            if type(value)is not bool:raise ChannelError('Boolean input requires bool')
        else:
            text(value)
            if graph.estimate(value)>declaration['max_tokens']:raise ChannelError('input exceeds declared bound')
        values[key]=value
    return values


class Kernel:
    def __init__(self,graph,document):
        fields(document,['format','version','defaults'],['rules','history_window'])
        if document['format']!=KERNEL_FORMAT or type(document['version'])is not int or document['version']!=1:
            raise ChannelError('unknown finite kernel format/version')
        self.graph=graph
        self.window=natural(document.get('history_window',0),upper=4)
        self.contracts={canonical(m):m for m in graph.models.values()}
        if not isinstance(document['defaults'],dict):raise ChannelError('defaults must be an object')
        self.defaults={}
        for alias,outcomes in document['defaults'].items():
            identity=self.model(alias);distribution=self.distribution(identity,outcomes)
            if identity in self.defaults and self.defaults[identity]!=distribution:
                raise ChannelError('same resolved contract has conflicting default kernels')
            self.defaults[identity]=distribution
        if set(self.defaults)!=set(self.contracts):raise ChannelError('each resolved graph contract needs a default kernel')
        rules=document.get('rules',[])
        if not isinstance(rules,list) or len(rules)>10000:raise ChannelError('rules must be a bounded array')
        self.rules=[]
        for rule in rules:
            fields(rule,['model','outcomes'],['template','arguments','ordinal','history'])
            identity=self.model(rule['model']);normalized={'identity':identity}
            if 'template'in rule:normalized['template']=text(rule['template'])
            if 'arguments'in rule:
                if not isinstance(rule['arguments'],list):raise ChannelError('rule arguments must be a text array')
                normalized['arguments']=[text(a) for a in rule['arguments']]
            if 'ordinal'in rule:normalized['ordinal']=natural(rule['ordinal'],upper=MAX_HORIZON)
            if 'history'in rule:
                history=rule['history']
                if not isinstance(history,list) or len(history)>self.window:raise ChannelError('rule history exceeds explicit window')
                normalized['history']=canonical([self.history_event(e) for e in history])
            normalized['outcomes']=self.distribution(identity,rule['outcomes']);self.rules.append(normalized)

    def model(self,alias):
        if not isinstance(alias,str) or alias not in self.graph.models:raise ChannelError('unknown kernel model alias')
        return canonical(self.graph.models[alias])

    def distribution(self,identity,outcomes):
        if not isinstance(outcomes,list) or not outcomes or len(outcomes)>256:raise ChannelError('outcomes must be a nonempty finite array')
        merged=defaultdict(Fraction)
        contract=self.contracts[identity]
        for outcome in outcomes:
            fields(outcome,['response','output_tokens','probability'])
            response=text(outcome['response']);usage=natural(outcome['output_tokens'],upper=contract['max_tokens'])
            if self.graph.estimate(response)>usage:raise ChannelError('response text does not fit reported output usage')
            merged[(response,usage)]=bounded_mass(merged[(response,usage)]+probability(outcome['probability']))
        total=Fraction()
        for p in merged.values():total=bounded_mass(total+p)
        if total!=1:raise ChannelError('outcome probabilities must sum exactly to one')
        return tuple((response,usage,p) for (response,usage),p in sorted(merged.items()))

    def history_event(self,event):
        fields(event,['contract','ordinal','template','arguments','response','input_tokens','output_tokens'])
        if canonical(event['contract'])not in self.contracts:raise ChannelError('history has unknown normalized contract')
        ordinal=natural(event['ordinal'],upper=MAX_HORIZON)
        template=text(event['template'])
        if not isinstance(event['arguments'],list):raise ChannelError('history arguments must be an array')
        arguments=[text(a) for a in event['arguments']];response=text(event['response'])
        identity=canonical(event['contract']);usage=natural(event['output_tokens'],upper=self.contracts[identity]['max_tokens'])
        if self.graph.estimate(response)>usage:raise ChannelError('invalid history response usage')
        input_usage=natural(event['input_tokens'])
        if input_usage!=self.graph.estimate(template)+sum(self.graph.estimate(a) for a in arguments):
            raise ChannelError('invalid complete history input usage')
        return {'contract':self.contracts[identity],'ordinal':ordinal,'template':template,'arguments':arguments,
                'response':response,'input_tokens':input_usage,'output_tokens':usage}

    def outcomes(self,identity,ordinal,template,arguments,history):
        history_json=canonical([json.loads(h) for h in history])
        for rule in self.rules:
            if rule['identity']!=identity:continue
            if 'ordinal'in rule and rule['ordinal']!=ordinal:continue
            if 'template'in rule and rule['template']!=template:continue
            if 'arguments'in rule and rule['arguments']!=arguments:continue
            if 'history'in rule and rule['history']!=history_json:continue
            return rule['outcomes']
        return self.defaults[identity]


def advance_control(graph,pc,values):
    """Normalize a deterministic control segment to its next call or stop."""
    for steps in range(1,MAX_CONTROL_STEPS+1):
        kind,event=graph.event(pc)
        if kind in ('call','stop'):return pc,kind,event,steps
        if kind=='goto':pc=(event['target'],0);continue
        guard=event['guard'];variable=guard['value']
        if variable not in values:raise ChannelError('guard reads uninitialized register')
        value=values[variable]
        if 'op'not in guard:branch=value
        else:
            a,b=graph.estimate(value),guard['limit']
            branch={'<':a<b,'<=':a<=b,'>':a>b,'>=':a>=b,'==':a==b,'!=':a!=b}[guard['op']]
        pc=(event['then'if branch else 'else'],0)
    raise ChannelLimit('deterministic control-step cap reached')


def observation(graph,contracts,billing,usage_trace,stopped,observer):
    if observer=='aggregate':
        vector=[{'contract':contracts[i],'call_count':row[0],'input_tokens':row[1],'output_tokens':row[2]}
                for i,row in enumerate(billing)]
        return canonical({'stopped':stopped,'billing':vector})
    return canonical({'stopped':stopped,'usage_trace':[json.loads(event)for event in usage_trace]})


def producer_histogram(graph_document,kernel_document,store,horizon,max_states=MAX_STATES,observer='aggregate',max_work_bytes=MAX_WORK_BYTES):
    """Return an exact DP channel row, or explicit UNKNOWN on resource limits.

    Equal states merge probability mass. The state includes all future-relevant
    values, per-contract ordinals, selected observation, and finite history.
    No partial histogram is reported as a completed/safe channel.
    """
    graph=Graph(bounded_document(graph_document))
    kernel=Kernel(graph,bounded_document(kernel_document))
    natural(horizon,upper=MAX_HORIZON,minimum=1);natural(max_states,upper=1000000,minimum=1)
    natural(max_work_bytes,upper=1024*1024*1024,minimum=1)
    if observer not in ('aggregate','trace'):raise ChannelError('unknown observer')
    values=normalized_store(graph,store)
    identities=sorted(kernel.contracts);contracts=[kernel.contracts[i]for i in identities]
    positions={identity:i for i,identity in enumerate(identities)}
    zero=tuple((0,0,0)for _ in identities)
    # (pc, value-map, ordinals, billing-vector, selected usage trace, window history, bytes-so-far)
    start=((graph.entry,0),tuple(sorted(values.items())),tuple(0 for _ in identities),zero,(),(),0)
    pending={start:Fraction(1)};histogram=defaultdict(Fraction)
    visited=peak=1;transitions=terminal_states=0
    work_bytes=0
    def charge(value):
        # A deterministic cumulative serialization-work estimate, not an RSS bound.
        nonlocal work_bytes
        work_bytes+=len(utf8(canonical(value)))+256
        if work_bytes>max_work_bytes:raise ChannelLimit('cumulative byte-work cap reached')
    try:
        charge(start)
        for depth in range(horizon+1):
            following=defaultdict(Fraction)
            for (pc,value_items,ordinals,billing,usage_trace,history,trace_bytes),mass in pending.items():
                values=dict(value_items);pc,kind,event,_=advance_control(graph,pc,values)
                if kind=='stop'or depth==horizon:
                    key=observation(graph,contracts,billing,usage_trace,kind=='stop',observer)
                    charge(key);histogram[key]=bounded_mass(histogram[key]+mass)
                    terminal_states+=1;continue
                contract=graph.models[event['model']];identity=canonical(contract);index=positions[identity]
                ordinal=ordinals[index]
                if any('value'in a and a['value']not in values for a in event['arguments']):
                    raise ChannelError('request reads uninitialized register')
                arguments=[a['literal']if'literal'in a else values[a['value']]for a in event['arguments']]
                request_bytes=len(utf8(event['template']))+sum(len(utf8(a))for a in arguments)
                if request_bytes>MAX_VALUE_BYTES:raise ChannelLimit('request byte cap reached')
                input_usage=graph.estimate(event['template'])+sum(graph.estimate(a)for a in arguments)
                input_bound=graph.estimate(event['template'])+sum(graph.argument_bound(a)for a in event['arguments'])
                if input_usage>input_bound:raise ChannelError('concrete request violates declared accounting bounds')
                for response,output_usage,p in kernel.outcomes(identity,ordinal,event['template'],arguments,history):
                    transitions+=1
                    byte_count=trace_bytes+request_bytes+len(utf8(response))
                    if byte_count>MAX_TRACE_BYTES:raise ChannelLimit('trace byte cap reached')
                    updated=dict(values);updated[event['result']]=response
                    updated_ordinals=list(ordinals);updated_ordinals[index]+=1
                    updated_billing=list(billing);count,input_total,output_total=billing[index]
                    updated_billing[index]=(count+1,input_total+input_usage,output_total+output_usage)
                    complete={'contract':contract,'ordinal':ordinal,'template':event['template'],'arguments':arguments,
                              'response':response,'input_tokens':input_usage,'output_tokens':output_usage}
                    updated_history=(history+(canonical(complete),))[-kernel.window:]if kernel.window else()
                    updated_trace=usage_trace+(canonical({'contract':contract,'input_tokens':input_usage,'output_tokens':output_usage}),)if observer=='trace'else()
                    next_state=((pc[0],pc[1]+1),tuple(sorted(updated.items())),tuple(updated_ordinals),
                                tuple(updated_billing),updated_trace,updated_history,byte_count)
                    charge(next_state)
                    if next_state not in following:
                        visited+=1
                        if visited>max_states:raise ChannelLimit('DP state resource cap reached')
                    following[next_state]=bounded_mass(following[next_state]+bounded_mass(mass*p))
            pending=dict(following);peak=max(peak,len(pending))
            if not pending:break
        total=exact_total(histogram.values())
        if total!=1:raise ChannelError('completed channel mass is not exactly one')
        return {'status':'complete','histogram':dict(sorted(histogram.items())),'mass':total,
                'state_visits':visited,'peak_frontier':peak,'call_transitions':transitions,
                'terminal_states':terminal_states,'observer':observer,'horizon':horizon,
                'work_bytes_estimate':work_bytes,'max_work_bytes':max_work_bytes}
    except ChannelLimit as error:
        return {'status':'unknown','reason':str(error),'histogram':None,'mass':None,
                'state_visits':visited,'peak_frontier':peak,'call_transitions':transitions,
                'observer':observer,'horizon':horizon,'work_bytes_estimate':work_bytes,
                'max_work_bytes':max_work_bytes}


def channel_metrics(histograms,priors):
    if not 2<=len(histograms)<=64 or len(histograms)!=len(priors):raise ChannelError('leakage metrics need 2..64 channel rows and matching priors')
    if any(not isinstance(p,Fraction)for p in priors):raise ChannelError('priors must be exact Fractions')
    if any(not isinstance(p,Fraction)or p<=0 for row in histograms for p in row.values()):
        raise ChannelError('channel probabilities must be positive exact Fractions')
    if any(p<=0 for p in priors)or exact_total(priors)!=1:raise ChannelError('prior must be positive and sum to one')
    if any(exact_total(row.values())!=1 for row in histograms):raise ChannelError('each channel row must have unit mass')
    outputs=sorted(set().union(*(row for row in histograms)))
    pairwise=[]
    for left,right in itertools.combinations(range(len(histograms)),2):
        tv=bounded_mass(exact_total(abs(histograms[left].get(b,Fraction())-histograms[right].get(b,Fraction()))for b in outputs)/2)
        ratios=[];infinite=False
        for a,c in ((left,right),(right,left)):
            for b in outputs:
                p,q=histograms[a].get(b,Fraction()),histograms[c].get(b,Fraction())
                if p and not q:infinite=True
                elif p and q:ratios.append(bounded_mass(p/q))
        maximum=None if infinite else max(ratios,default=Fraction(1))
        pairwise.append({'left':left,'right':right,'total_variation':str(tv),
                         'equal_observation_laws':tv==0,'maximum_likelihood_ratio':None if infinite else str(maximum),
                         'maximum_log_likelihood_ratio_nats_approx':None if infinite else math.log(maximum.numerator)-math.log(maximum.denominator),
                         'infinite_likelihood_ratio':infinite})
    marginal={b:exact_total(bounded_mass(priors[s]*histograms[s].get(b,Fraction()))for s in range(len(histograms)))for b in outputs}
    vulnerability=exact_total(max(bounded_mass(priors[s]*histograms[s].get(b,Fraction()))for s in range(len(histograms)))for b in outputs)
    prior_vulnerability=max(priors);terms=[];mi=0.0
    for s,row in enumerate(histograms):
        for b,p in row.items():
            coefficient=bounded_mass(priors[s]*p);ratio=bounded_mass(p/marginal[b])
            terms.append({'coefficient':str(coefficient),'ratio':str(ratio)})
            mi+=float(coefficient)*(math.log2(ratio.numerator)-math.log2(ratio.denominator))
    # The exact expression above remains authoritative; this float display has no certified interval.
    return {'pairwise':pairwise,'bayes_vulnerability':str(vulnerability),
            'prior_bayes_vulnerability':str(prior_vulnerability),
            'min_entropy_vulnerability_ratio':str(vulnerability/prior_vulnerability),
            'min_entropy_leakage_bits_approx':math.log2(vulnerability/prior_vulnerability),
            'mutual_information_bits_approx':max(0.0,mi),
            'mutual_information_exact_expression':{'form':'sum(coefficient * log2(ratio))','terms':terms},
            'all_pairwise_observation_laws_equal':all(row['equal_observation_laws']for row in pairwise),
            'limits':['exact probabilities/TV/vulnerability; log displays are floating approximations',
                      'likelihood ratio is a channel statistic, not a differential-privacy claim without declared adjacency']}


def analyze(graph_document,kernel_document,public_store,secret_scenarios,horizon,max_states=MAX_STATES,observer='aggregate',max_work_bytes=MAX_WORK_BYTES):
    graph=Graph(bounded_document(graph_document))
    public={v for v,d in graph.inputs.items()if d['label']=='public'}
    secret=set(graph.inputs)-public
    if not isinstance(public_store,dict)or set(public_store)!=public:raise ChannelError('public store must contain exactly public inputs')
    if not isinstance(secret_scenarios,list)or not 2<=len(secret_scenarios)<=64:raise ChannelError('leakage analysis needs 2..64 explicit secret scenarios')
    rows=[];priors=[];stores=set()
    for scenario in secret_scenarios:
        fields(scenario,['values','prior'])
        if not isinstance(scenario['values'],dict)or set(scenario['values'])!=secret:raise ChannelError('scenario must contain exactly secret inputs')
        store={**public_store,**scenario['values']};normalized_store(graph,store)
        identity=canonical(scenario['values'])
        if identity in stores:raise ChannelError('duplicate secret scenario')
        stores.add(identity);priors.append(probability(scenario['prior']))
        row=producer_histogram(graph_document,kernel_document,store,horizon,max_states,observer,max_work_bytes)
        rows.append(row)
    if exact_total(priors)!=1:raise ChannelError('scenario priors must sum to one')
    if any(row['status']!='complete'for row in rows):
        return {'status':'unknown','rows':rows,'metrics':None,'observer':observer,'horizon':horizon,
                'public_store':public_store,'secret_scenarios':secret_scenarios}
    try:metrics=channel_metrics([r['histogram']for r in rows],priors)
    except ChannelLimit as error:
        for row in rows:row.update(status='unknown',reason=str(error),histogram=None,mass=None)
        return {'status':'unknown','reason':str(error),'rows':rows,'metrics':None,'observer':observer,'horizon':horizon,
                'public_store':public_store,'secret_scenarios':secret_scenarios}
    return {'status':'complete','rows':rows,'metrics':metrics,
            'observer':observer,'horizon':horizon,'priors':[str(p)for p in priors],
            'public_store':public_store,'secret_scenarios':secret_scenarios}


def serialize(result):
    if isinstance(result,Fraction):return str(result)
    if isinstance(result,dict):
        if 'histogram'in result and isinstance(result['histogram'],dict):
            return {**{k:serialize(v)for k,v in result.items()if k!='histogram'},
                    'histogram':[{'observation':json.loads(k),'probability':str(p)}for k,p in result['histogram'].items()]}
        return {k:serialize(v)for k,v in result.items()}
    if isinstance(result,(list,tuple)):return [serialize(v)for v in result]
    return result


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('graph',type=Path);cli.add_argument('kernel',type=Path)
    cli.add_argument('--public-json',required=True);cli.add_argument('--scenarios-json',required=True)
    cli.add_argument('--horizon',type=int,default=8);cli.add_argument('--max-states',type=int,default=MAX_STATES)
    cli.add_argument('--max-work-bytes',type=int,default=MAX_WORK_BYTES)
    cli.add_argument('--observer',choices=('aggregate','trace'),default='aggregate');cli.add_argument('--report',type=Path)
    args=cli.parse_args()
    try:
        with args.graph.open('rb')as stream:raw_graph=stream.read(MAX_SOURCE_BYTES+1)
        with args.kernel.open('rb')as stream:raw_kernel=stream.read(MAX_SOURCE_BYTES+1)
        if len(raw_graph)>MAX_SOURCE_BYTES or len(raw_kernel)>MAX_SOURCE_BYTES:raise ChannelLimit('source byte cap reached')
        if len(utf8(args.public_json))+len(utf8(args.scenarios_json))>MAX_SOURCE_BYTES:
            raise ChannelLimit('input scenario byte cap reached')
        public_store=strict_json(args.public_json);scenarios=strict_json(args.scenarios_json)
        result=analyze(strict_json(raw_graph),strict_json(raw_kernel),public_store,
                       scenarios,args.horizon,args.max_states,args.observer,args.max_work_bytes)
        result=serialize(result)
        result.update(format='orchlang-finite-usage-channel',version=1,source_sha256=sha(raw_graph),
                      kernel_sha256=sha(raw_kernel),analyzer_sha256=sha(Path(__file__).read_bytes()),
                      public_store_sha256=sha(utf8(canonical(public_store))),
                      secret_scenarios_sha256=sha(utf8(canonical(scenarios))),
                      max_states=args.max_states,max_work_bytes=args.max_work_bytes,
                      rule_precedence='first matching rule in supplied order, otherwise resolved-contract default',
                      scope='success-only integer usage plus stop/truncation under declared finite rational conditional kernels; no currency, errors, provider estimates or infinite-run law')
        encoded=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
        if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(encoded,encoding='utf-8')
        print(encoded,end='');return 0 if result['status']=='complete'else 2
    except (ChannelError,InvalidGraph,OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError)as error:
        print('finite channel analysis failed closed: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
