"""Sequential per-model reservation ledger; units are never added across models.

This is runtime admission, not an affine ownership system or a static proof.
Unconfirmed dispatches retain their reservation and make actual usage incomplete.
"""
from copy import deepcopy


class AdmissionRefused(ValueError):
    pass


class UsageLedger:
    def __init__(self, limits=None):
        self.limits=deepcopy(limits or {})
        self.rows={};self.pending={};self.next_attempt=0
        for model,limit in self.limits.items():
            if not isinstance(model,str) or set(limit)-{'input','output','calls'}:
                raise ValueError('invalid model-unit budget')
            if any(type(v) is not int or v<0 for v in limit.values()):
                raise ValueError('budget values must be nonnegative integers')

    def admit_shape(self, shape):
        """Admit a complete constant shape before evaluating any input value.

        A missing shape gives no whole-workflow guarantee; per-call reservations
        still apply. Tools are observed but are not charged in model token units.
        """
        if shape is None:
            return
        totals={}
        for event in shape:
            if event[0]!='llm':
                continue
            _,model,input_tokens,output_tokens=event
            row=totals.setdefault(model,dict(input=0,output=0,calls=0))
            row['input']+=input_tokens;row['output']+=output_tokens;row['calls']+=1
        for model,row in totals.items():
            if any(row[key]>limit for key,limit in self.limits.get(model,{}).items()):
                raise AdmissionRefused('complete workflow shape exceeds model-unit budget')

    def reserve(self, model, request_tokens, output_cap):
        if any(type(v) is not int or v<0 for v in (request_tokens,output_cap)):
            raise ValueError('invalid reservation')
        row=self.rows.setdefault(model,dict(input=0,output=0,calls=0))
        request=dict(input=request_tokens,output=output_cap,calls=1)
        held={key:row[key]+sum(r[key] for m,r in self.pending.values() if m==model) for key in request}
        if any(held[key]+request[key]>limit for key,limit in self.limits.get(model,{}).items()):
            raise AdmissionRefused('model-unit resource reservation exceeds remaining budget')
        attempt=self.next_attempt;self.next_attempt+=1
        self.pending[attempt]=(model,request)
        return attempt

    def confirm(self, attempt, input_tokens, output_tokens):
        model,reservation=self.pending[attempt]
        if type(input_tokens) is not int or type(output_tokens) is not int or input_tokens!=reservation['input'] or not 0<=output_tokens<=reservation['output']:
            raise ValueError('actual usage does not refine the reservation')
        row=self.rows[model]
        row['input']+=input_tokens;row['output']+=output_tokens;row['calls']+=1
        del self.pending[attempt]

    def snapshot(self):
        return dict(confirmed=deepcopy(self.rows),usage_complete=not self.pending,
                    unconfirmed=[dict(attempt=i,model=m,reservation=deepcopy(r)) for i,(m,r) in self.pending.items()],
                    unit='model-contract-indexed logical input/output token counts and call counts',
                    limits=deepcopy(self.limits))
