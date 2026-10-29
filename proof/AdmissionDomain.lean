import ShapeCore

namespace OrchLang.Shape

/-! ### Restricted-domain conformance and visible completion status

Unlike World.Conforms, ConformsOn asks nothing of an oversized or otherwise
unsupported request. RunsIn checks only calls reached by this execution,
including cover calls. It is a premise, not a claim that static source caps
prove admission. Finite exhaustive replay can check a finite domain; universal
or stochastic deployment domains require an invariant/refinement proof.
-/

abbrev RequestDomain := String → Nat → Nat → String → Prop

def World.ConformsOn (w : World) (D : RequestDomain) : Prop :=
  ∀ m T N r, D m T N r →
    w.tok m (w.padReq m T r) = T ∧
    ∀ c, w.outTok m (w.forced m (w.padReq m T r) c N) = N

def CoverIn (w : World) (D : RequestDomain) (sh : List Event) : Prop :=
  ∀ e ∈ sh, match e with
    | .llm m T N => D m T N w.dummyReq
    | .tool _ => True

def loopIn (step : St → St) (P : St → Prop) (cover : Prop)
    (g : Guard) (padded : Bool) : Nat → St → Prop
  | 0, _ => True
  | n+1, s => if holds s.store g then (if padded then cover else True)
      else P s ∧ loopIn step P cover g padded n (step s)

def RunsIn (w : World) (ω : Nat → Nat → Nat) (D : RequestDomain) : Stmt → St → Prop
  | .skip, _ => True
  | .seq a b, s => RunsIn w ω D a s ∧ RunsIn w ω D b (exec w ω a s)
  | .call _ _ m _ e (some (T,N)), s => D m T N (evalE s.store e)
  | .call _ _ _ _ _ none, _ => True
  | .tool _ _ _, _ => True
  | .dummy m T N, _ => D m T N w.dummyReq
  | .dummyTool _, _ => True
  | .ite g a b, s => if holds s.store g then RunsIn w ω D a s else RunsIn w ω D b s
  | .loop n g body padded, s =>
      loopIn (exec w ω body) (RunsIn w ω D body)
        (CoverIn w D ((shape body).getD [])) g padded n s

theorem cover_map_on (w : World) (D : RequestDomain) (hw : w.ConformsOn D)
    (sh : List Event) (h : CoverIn w D sh) : sh.map (ghostEvent w) = sh := by
  induction sh with
  | nil => rfl
  | cons e tail ih =>
      have he := h e (by simp)
      have ht : CoverIn w D tail := fun x hx => h x (by simp [hx])
      cases e with
      | tool t => simp [ghostEvent, ih ht]
      | llm m T N =>
          have hc := hw m T N w.dummyReq he
          simp [ghostEvent, dummyEvent, hc.1, hc.2, ih ht]

theorem loop_trace_on (step ghostStep : St → St) (P : St → Prop) (cover : Prop)
    (g : Guard) (x : List Event)
    (hs : ∀ s, P s → (step s).trace = s.trace ++ x)
    (hg : cover → ∀ s, (ghostStep s).trace = s.trace ++ x) :
    ∀ n s, loopIn step P cover g true n s →
      (loopRun step ghostStep g true n s).trace = s.trace ++ rep n x := by
  intro n
  induction n with
  | zero => intro s _; simp [loopRun, rep]
  | succ n ih =>
      intro s h
      by_cases hh : holds s.store g = true
      · have hc : cover := by simpa [loopIn, hh] using h
        simp [loopRun, hh, iter_trace ghostStep x (hg hc)]
      · have hc : P s ∧ loopIn step P cover g true n (step s) := by
          simpa [loopIn, hh] using h
        simp [loopRun, hh, ih _ hc.2, hs _ hc.1, rep_succ', rep]

theorem shape_exec_on (w : World) (ω : Nat → Nat → Nat) (D : RequestDomain)
    (hw : w.ConformsOn D) :
    ∀ p sh, shape p = some sh → ∀ s, RunsIn w ω D p s →
      (exec w ω p s).trace = s.trace ++ sh := by
  intro p
  induction p with
  | skip => intro sh h s _; simp [shape] at h; subst h; simp [exec]
  | seq a b iha ihb =>
      intro sh h s hd
      obtain ⟨hda,hdb⟩ := hd
      cases ha : shape a with
      | none => simp [shape, ha] at h
      | some x =>
          cases hb : shape b with
          | none => simp [shape, ha, hb] at h
          | some y =>
              simp [shape, ha, hb] at h; subst h
              simp [exec, ihb y hb _ hdb, iha x ha _ hda]
  | call i x m k e pad =>
      intro sh h s hd
      cases pad with
      | none => simp [shape] at h
      | some tn =>
          obtain ⟨T,N⟩ := tn
          simp [shape] at h; subst h
          have hc := hw m T N (evalE s.store e) hd
          simp [exec, hc.1, hc.2]
  | tool x t e => intro sh h s _; simp [shape] at h; subst h; simp [exec]
  | dummy m T N =>
      intro sh h s hd
      simp [shape] at h; subst h
      have hc := hw m T N w.dummyReq hd
      simp [exec, dummyEvent, hc.1, hc.2]
  | dummyTool t => intro sh h s _; simp [shape] at h; subst h; simp [exec]
  | ite g a b iha ihb =>
      intro sh h s hd
      cases ha : shape a with
      | none => simp [shape, ha] at h
      | some x =>
          cases hb : shape b with
          | none => simp [shape, ha, hb] at h
          | some y =>
              by_cases hxy : x = y
              · subst hxy
                simp [shape, ha, hb] at h; subst h
                by_cases hh : holds s.store g = true
                · have hr : RunsIn w ω D a s := by simpa [RunsIn, hh] using hd
                  simp [exec, hh, iha _ ha _ hr]
                · have hr : RunsIn w ω D b s := by simpa [RunsIn, hh] using hd
                  simp [exec, hh, ihb _ hb _ hr]
              · simp [shape, ha, hb, hxy] at h
  | loop n g body padded ih =>
      intro sh h s hd
      cases padded with
      | false => simp [shape] at h
      | true =>
          cases hb : shape body with
          | none => simp [shape, hb] at h
          | some x =>
              simp [shape, hb] at h; subst h
              simp only [exec, hb, Option.getD]
              apply loop_trace_on (exec w ω body) (ghost w x) (RunsIn w ω D body)
                (CoverIn w D x) g x
              · intro st hr; exact ih x hb st hr
              · intro hc st; simp [ghost, cover_map_on w D hw x hc]
              · simpa [RunsIn, hb] using hd

inductive CompletionObservation where
  | refused
  | completed (trace : List Event)
  | failed (confirmedPrefix : List Event)
  | unknownDispatch (confirmedPrefix : List Event)
deriving DecidableEq, Repr

/-- Explicit ideal admission semantics. Fail/unknown are in the observation
    alphabet but cannot occur in this ideal successful-execution adapter.
    No refinement claim about Python exceptions follows from this definition. -/
noncomputable def domainObservation (w : World) (ω : Nat → Nat → Nat)
    (D : RequestDomain) (p : Stmt) (s : St) : CompletionObservation := by
  classical
  exact if RunsIn w ω D p s then .completed (exec w ω p s).trace else .refused

theorem admitted_noninterference (w : World) (ω : Nat → Nat → Nat) (D : RequestDomain)
    (hw : w.ConformsOn D) (p : Stmt) (sh : List Event) (hs : shape p = some sh)
    (s t : St) (htr : s.trace = t.trace)
    (hadmit : RunsIn w ω D p s ↔ RunsIn w ω D p t) :
    domainObservation w ω D p s = domainObservation w ω D p t := by
  classical
  by_cases h : RunsIn w ω D p s
  · have ht := hadmit.mp h
    simp [domainObservation, h, ht, shape_exec_on w ω D hw p sh hs s h,
      shape_exec_on w ω D hw p sh hs t ht, htr]
  · have ht : ¬ RunsIn w ω D p t := fun ht => h (hadmit.mpr ht)
    simp [domainObservation, h, ht]

/-- A public input domain certificate supplies the missing all-inputs invariant.
    It must cover every tape, including reachable intermediate requests/dummies. -/
def DomainCertificate (w : World) (D : RequestDomain) (p : Stmt) (inputs : Store → Prop) : Prop :=
  ∀ σ, inputs σ → ∀ ω, RunsIn w ω D p ⟨σ, fun _ => 0, []⟩

theorem certified_domain_noninterference (w : World) (D : RequestDomain)
    (hw : w.ConformsOn D) (p : Stmt) (sh : List Event) (hs : shape p = some sh)
    (inputs : Store → Prop) (hc : DomainCertificate w D p inputs)
    (σ τ : Store) (hσ : inputs σ) (hτ : inputs τ) (ω : Nat → Nat → Nat) :
    domainObservation w ω D p ⟨σ,fun _ => 0,[]⟩ = .completed sh ∧
    domainObservation w ω D p ⟨τ,fun _ => 0,[]⟩ = .completed sh := by
  classical
  constructor
  · simp [domainObservation, hc σ hσ ω, shape_exec_on w ω D hw p sh hs _ (hc σ hσ ω)]
  · simp [domainObservation, hc τ hτ ω, shape_exec_on w ω D hw p sh hs _ (hc τ hτ ω)]

/-! ### Compositional static admission

The certificate below does not execute the program or quantify over future
responses. A finite vector bounds store values. Primitive expansion and output
bounds are explicit world contracts; a concrete tokenizer/backend must discharge
them before this certificate can justify physical admission. No such contract is
asserted for the heuristic sizing used in the retained application campaign.
-/

structure Envelope where
  size : String → Nat
  alpha : String → Nat
  overhead : String → Nat
  response : String → Nat → Nat
  tool : String → Nat
  context : String → Nat

def Envelope.Sound (b : Envelope) (w : World) : Prop :=
  (∀ a c, b.size (a ++ c) ≤ b.size a + b.size c) ∧
  (∀ a, b.size (escapeText a) ≤ 2 * b.size a) ∧
  (∀ a, b.size (trimText a) ≤ b.size a) ∧
  (∀ m r, w.tok m r ≤ b.alpha m * b.size r + b.overhead m) ∧
  (∀ m k T N r c, k ≤ N →
    b.size (w.view m k (w.forced m (w.padReq m T r) c N)) ≤ b.response m k) ∧
  (∀ t r, b.size (w.toolFn t r) ≤ b.tool t)

abbrev ValueBounds := List Nat
def boundedStore (b : Envelope) (v : ValueBounds) (σ : Store) : Prop :=
  ∀ x, b.size (σ x) ≤ v[x]?.getD 0

def boundE (b : Envelope) (v : ValueBounds) : Expr → Nat
  | .lit r => b.size r
  | .var x => v[x]?.getD 0
  | .app a c => boundE b v a + boundE b v c
  | .escape e => 2 * boundE b v e
  | .trim e => boundE b v e

def envelopeDomain (w : World) (b : Envelope) : RequestDomain :=
  fun m T N r => w.tok m r ≤ T ∧ T + N ≤ b.context m

def coverCertificate (w : World) (b : Envelope) (sh : List Event) : Bool :=
  sh.all fun e => match e with
    | .llm m T N => decide (w.tok m w.dummyReq ≤ T ∧ T + N ≤ b.context m)
    | .tool _ => true

/-- A decidable compositional checker; it never evaluates exec or RunsIn. -/
def staticCertificate (w : World) (b : Envelope) (v : ValueBounds) : Stmt → Bool
  | .skip => true
  | .seq a c => staticCertificate w b v a && staticCertificate w b v c
  | .call _ x m k e (some (T,N)) => decide
      (b.alpha m * boundE b v e + b.overhead m ≤ T ∧
       T + N ≤ b.context m ∧ k ≤ N ∧ b.response m k ≤ v[x]?.getD 0)
  | .call _ _ _ _ _ none => false
  | .tool x t _ => decide (b.tool t ≤ v[x]?.getD 0)
  | .dummy m T N => decide (w.tok m w.dummyReq ≤ T ∧ T + N ≤ b.context m)
  | .dummyTool _ => true
  | .ite _ a c => staticCertificate w b v a && staticCertificate w b v c
  | .loop _ _ body padded => staticCertificate w b v body &&
      (!padded || coverCertificate w b ((shape body).getD []))

theorem boundE_sound (b : Envelope) (w : World) (hb : b.Sound w)
    (v : ValueBounds) (σ : Store) (hv : boundedStore b v σ) (e : Expr) :
    b.size (evalE σ e) ≤ boundE b v e := by
  induction e with
  | lit r => exact Nat.le_refl _
  | var x => exact hv x
  | app a c iha ihc => exact Nat.le_trans (hb.1 _ _) (Nat.add_le_add iha ihc)
  | escape e ih => exact Nat.le_trans (hb.2.1 _) (Nat.mul_le_mul_left 2 ih)
  | trim e ih => exact Nat.le_trans (hb.2.2.1 _) ih

theorem boundedStore_upd (b : Envelope) (v : ValueBounds) (σ : Store)
    (hv : boundedStore b v σ) (x : Var) (r : String)
    (hr : b.size r ≤ v[x]?.getD 0) : boundedStore b v (upd σ x r) := by
  intro y
  by_cases h : y = x
  · subst y; simpa [upd] using hr
  · simpa [upd, h] using hv y

theorem coverCertificate_sound (w : World) (b : Envelope) (sh : List Event)
    (h : coverCertificate w b sh = true) : CoverIn w (envelopeDomain w b) sh := by
  intro e he
  have hh := List.all_eq_true.mp h e he
  cases e with
  | tool t => trivial
  | llm m T N => simpa [envelopeDomain] using hh

theorem loopIn_invariant (step : St → St) (P : St → Prop) (cover : Prop)
    (inv : St → Prop) (g : Guard) (padded : Bool)
    (hstep : ∀ s, inv s → P s ∧ inv (step s))
    (hc : padded = true → cover) : ∀ n s, inv s →
      loopIn step P cover g padded n s := by
  intro n
  induction n with
  | zero => intro s _; trivial
  | succ n ih =>
      intro s hs
      simp only [loopIn]
      split
      · split
        · exact hc (by assumption)
        · trivial
      · exact ⟨(hstep s hs).1, ih _ (hstep s hs).2⟩

theorem loopRun_invariant (step ghostStep : St → St) (inv : St → Prop)
    (g : Guard) (padded : Bool)
    (hs : ∀ s, inv s → inv (step s)) (hg : ∀ s, inv s → inv (ghostStep s)) :
    ∀ n s, inv s → inv (loopRun step ghostStep g padded n s) := by
  have hi : ∀ n s, inv s → inv (iter ghostStep n s) := by
    intro n; induction n with
    | zero => intro s h; exact h
    | succ n ih => intro s h; exact ih _ (hg s h)
  intro n
  induction n with
  | zero => intro s h; exact h
  | succ n ih =>
      intro s h
      simp only [loopRun]
      split
      · split
        · exact hi _ s h
        · exact h
      · exact ih _ (hs s h)

theorem static_certificate_sound (w : World) (b : Envelope) (hb : b.Sound w)
    (v : ValueBounds) (ω : Nat → Nat → Nat) (p : Stmt)
    (hc : staticCertificate w b v p = true) : ∀ s, boundedStore b v s.store →
      RunsIn w ω (envelopeDomain w b) p s ∧
      boundedStore b v (exec w ω p s).store := by
  induction p with
  | skip => intro s h; exact ⟨True.intro, h⟩
  | seq a c iha ihc =>
      have hh : staticCertificate w b v a = true ∧ staticCertificate w b v c = true := by
        simpa only [staticCertificate, Bool.and_eq_true] using hc
      intro s h
      have ha := iha hh.1 s h
      have hcc := ihc hh.2 _ ha.2
      exact ⟨⟨ha.1, hcc.1⟩, hcc.2⟩
  | call i x m k e pad =>
      cases pad with
      | none => simp [staticCertificate] at hc
      | some tn =>
          obtain ⟨T,N⟩ := tn
          have hh : b.alpha m * boundE b v e + b.overhead m ≤ T ∧
              T + N ≤ b.context m ∧ k ≤ N ∧ b.response m k ≤ v[x]?.getD 0 := by
            simpa [staticCertificate] using hc
          intro s h
          have ht := hb.2.2.2.1 m (evalE s.store e)
          have he := boundE_sound b w hb v s.store h e
          have hr := Nat.le_trans ht (Nat.le_trans
            (Nat.add_le_add_right (Nat.mul_le_mul_left (b.alpha m) he) _) hh.1)
          refine ⟨⟨hr, hh.2.1⟩, ?_⟩
          apply boundedStore_upd b v s.store h x
          exact Nat.le_trans (hb.2.2.2.2.1 m k T N _ _ hh.2.2.1) hh.2.2.2
  | tool x t e =>
      have hh : b.tool t ≤ v[x]?.getD 0 := by simpa [staticCertificate] using hc
      intro s h
      exact ⟨True.intro, boundedStore_upd b v s.store h x _
        (Nat.le_trans (hb.2.2.2.2.2 t _) hh)⟩
  | dummy m T N =>
      intro s h
      exact ⟨by simpa [staticCertificate, RunsIn, envelopeDomain] using hc, h⟩
  | dummyTool t => intro s h; exact ⟨True.intro, h⟩
  | ite g a c iha ihc =>
      have hh : staticCertificate w b v a = true ∧ staticCertificate w b v c = true := by
        simpa only [staticCertificate, Bool.and_eq_true] using hc
      intro s h
      by_cases hg : holds s.store g = true
      · simpa [RunsIn, exec, hg] using iha hh.1 s h
      · simpa [RunsIn, exec, hg] using ihc hh.2 s h
  | loop n g body padded ih =>
      have hh : staticCertificate w b v body = true ∧
          (!padded || coverCertificate w b ((shape body).getD [])) = true := by
        simpa only [staticCertificate, Bool.and_eq_true] using hc
      have hstep := ih hh.1
      have hcover : padded = true → CoverIn w (envelopeDomain w b) ((shape body).getD []) := by
        intro hp
        apply coverCertificate_sound
        simpa [hp] using hh.2
      intro s h
      constructor
      · exact loopIn_invariant _ _ _ (fun st => boundedStore b v st.store)
          g padded hstep hcover n s h
      · exact loopRun_invariant (exec w ω body) (ghost w ((shape body).getD []))
          (fun st => boundedStore b v st.store) g padded
          (fun st hv => (hstep st hv).2) (fun _ hv => hv) n s h

theorem static_certificate_implies_RunsIn (w : World) (b : Envelope) (hb : b.Sound w)
    (v : ValueBounds) (p : Stmt) (hc : staticCertificate w b v p = true)
    (σ : Store) (hσ : boundedStore b v σ) (ω : Nat → Nat → Nat) :
    RunsIn w ω (envelopeDomain w b) p ⟨σ, fun _ => 0, []⟩ :=
  (static_certificate_sound w b hb v ω p hc _ hσ).1

theorem static_certificate_domain (w : World) (b : Envelope) (hb : b.Sound w)
    (v : ValueBounds) (p : Stmt) (hc : staticCertificate w b v p = true) :
    DomainCertificate w (envelopeDomain w b) p (boundedStore b v) := by
  intro σ hσ ω
  exact static_certificate_implies_RunsIn w b hb v p hc σ hσ ω

#print axioms static_certificate_implies_RunsIn
#print axioms static_certificate_domain
#print axioms shape_exec_on
#print axioms admitted_noninterference
#print axioms certified_domain_noninterference

end OrchLang.Shape
