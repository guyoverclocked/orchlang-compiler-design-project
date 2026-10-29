import Lean

/- Shape-padding core for usage-metadata noninterference.

   An observer sees the ordered usage trace of a workflow run: for every model
   call the model name, input-token count and output-token count; for every tool
   call its name. Request and response contents are hidden from the observer
   but flow through the workflow store, where later requests and guards may
   depend on them.

   Model randomness is a tape `ω site k`: the k-th execution of call site
   `site` reads cell `ω site k`. For any tape distribution in which the cells
   are i.i.d., this realizes fresh per-call randomness, so pointwise equality
   of traces for every tape implies equality of trace distributions.

   Assumptions are explicit hypotheses, not axioms:
   * `World.Conforms`: padding a request to `T` tokens yields exactly `T`
     tokens and forced decoding to `N` tokens yields exactly `N` tokens.
   * `World.Transparent` (functional preservation only): the visible part of a
     padded, forced response equals the unpadded response for the same cell.
   No tokenizer, serving system, parser or compiler is verified here. -/
namespace OrchLang.Shape

inductive Label where
  | low
  | high
deriving DecidableEq, Repr

def Label.join : Label → Label → Label
  | .low, l => l
  | .high, _ => .high

def Label.le : Label → Label → Bool
  | .low, _ => true
  | .high, .high => true
  | .high, .low => false

abbrev Var := Nat
abbrev Store := Var → String
abbrev Ctx := Var → Label

inductive Expr where
  | lit (value : String)
  | var (x : Var)
  | app (a b : Expr)
  | escape (value : Expr)
  | trim (value : Expr)
deriving DecidableEq, Repr

inductive Guard where
  | eq (x : Var) (value : String)
  | prefix (x : Var) (value : String)
deriving DecidableEq, Repr

inductive Event where
  | llm (model : String) (input output : Nat)
  | tool (name : String)
deriving DecidableEq, Repr

inductive Stmt where
  | skip
  | seq (a b : Stmt)
  | call (site : Nat) (x : Var) (model : String) (cap : Nat) (req : Expr) (pad : Option (Nat × Nat))
  | tool (x : Var) (name : String) (arg : Expr)
  | dummy (model : String) (input output : Nat)
  | dummyTool (name : String)
  | ite (g : Guard) (a b : Stmt)
  | loop (n : Nat) (g : Guard) (body : Stmt) (padded : Bool)
deriving DecidableEq, Repr

structure World where
  tok : String → String → Nat
  gen : String → String → Nat → Nat → String
  forced : String → String → Nat → Nat → String
  view : String → Nat → String → String
  padReq : String → Nat → String → String
  outTok : String → String → Nat
  toolFn : String → String → String
  dummyReq : String

def World.Conforms (w : World) : Prop :=
  (∀ m T r, w.tok m (w.padReq m T r) = T) ∧
  (∀ m r c N, w.outTok m (w.forced m r c N) = N)

def World.Transparent (w : World) : Prop :=
  ∀ m k T N r c, k ≤ N → w.view m k (w.forced m (w.padReq m T r) c N) = w.gen m r k c

structure St where
  store : Store
  count : Nat → Nat
  trace : List Event

def upd (σ : Store) (x : Var) (v : String) : Store := fun y => if y = x then v else σ y
def bump (c : Nat → Nat) (i : Nat) : Nat → Nat := fun j => if j = i then c i + 1 else c j

-- Python/Jinja whitespace, including the Unicode cases omitted by Lean's
-- ASCII Char.isWhitespace. Its finite classification is checked in the adapter
-- regressions; no concrete template parser is part of the core proof.
def templateWhitespace (c : Char) : Bool :=
  ([9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,
    8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288] : List Nat).contains c.toNat

def trimText (text : String) : String :=
  String.mk (((text.toList.dropWhile templateWhitespace).reverse.dropWhile templateWhitespace).reverse)

/-- Tool-argument escaping, defined character-wise: a backslash is doubled and
    the unit separator U+001F becomes the two characters `\s`. This equals the
    Python adapter's sequential `replace` (the first rewrite introduces no U+001F
    and the second rewrite runs after backslashes are doubled). -/
def escapeChar (c : Char) : List Char :=
  if c.toNat = 92 then [c, c] else if c.toNat = 31 then [Char.ofNat 92, 's'] else [c]

def escapeText (text : String) : String := String.mk (text.toList.flatMap escapeChar)

-- Executable agreement with the sequential replacement used by the adapter.
private def escapeByReplace (text : String) : String :=
  (text.replace "\\" "\\\\").replace (String.mk [Char.ofNat 31]) "\\s"
#guard ["", "plain", "a\\b", "\\\\", "x\x1fy", "\x1f\\\x1f", "é\\ü\x1f€"].all
  fun t => escapeText t == escapeByReplace t

def evalE (σ : Store) : Expr → String
  | .lit s => s
  | .var x => σ x
  | .app a b => evalE σ a ++ evalE σ b
  | .escape e => escapeText (evalE σ e)
  | .trim e => trimText (evalE σ e)

def holds (σ : Store) : Guard → Bool
  | .eq x s => σ x == s
  | .prefix x s => s.isPrefixOf (σ x)

def guardVar : Guard → Var
  | .eq x _ => x
  | .prefix x _ => x

def rep : Nat → List Event → List Event
  | 0, _ => []
  | n+1, x => x ++ rep n x

/-- Static usage shape: defined exactly when every run emits the same trace. -/
def shape : Stmt → Option (List Event)
  | .skip => some []
  | .seq a b =>
      match shape a, shape b with
      | some x, some y => some (x ++ y)
      | _, _ => none
  | .call _ _ m _ _ (some (T, N)) => some [.llm m T N]
  | .call _ _ _ _ _ none => none
  | .tool _ t _ => some [.tool t]
  | .dummy m T N => some [.llm m T N]
  | .dummyTool t => some [.tool t]
  | .ite _ a b =>
      match shape a, shape b with
      | some x, some y => if x = y then some x else none
      | _, _ => none
  | .loop n _ body true =>
      match shape body with
      | some x => some (rep n x)
      | none => none
  | .loop _ _ _ false => none

def dummyEvent (w : World) (m : String) (T N : Nat) : Event :=
  let r := w.padReq m T w.dummyReq
  .llm m (w.tok m r) (w.outTok m (w.forced m r 0 N))

def ghostEvent (w : World) : Event → Event
  | .llm m T N => dummyEvent w m T N
  | .tool t => .tool t

/-- One dummy iteration of a padded loop: emits the body's shape, touches no
    store entry and reads no randomness cell. -/
def ghost (w : World) (sh : List Event) (s : St) : St :=
  { s with trace := s.trace ++ sh.map (ghostEvent w) }

def iter (f : St → St) : Nat → St → St
  | 0, s => s
  | n+1, s => iter f n (f s)

def loopRun (step ghostStep : St → St) (g : Guard) (padded : Bool) : Nat → St → St
  | 0, s => s
  | n+1, s =>
      if holds s.store g then (if padded then iter ghostStep (n+1) s else s)
      else loopRun step ghostStep g padded n (step s)

def exec (w : World) (ω : Nat → Nat → Nat) : Stmt → St → St
  | .skip, s => s
  | .seq a b, s => exec w ω b (exec w ω a s)
  | .call i x m k e none, s =>
      let r := evalE s.store e
      let resp := w.gen m r k (ω i (s.count i))
      { store := upd s.store x resp, count := bump s.count i,
        trace := s.trace ++ [.llm m (w.tok m r) (w.outTok m resp)] }
  | .call i x m k e (some (T, N)), s =>
      let r := w.padReq m T (evalE s.store e)
      let resp := w.forced m r (ω i (s.count i)) N
      { store := upd s.store x (w.view m k resp), count := bump s.count i,
        trace := s.trace ++ [.llm m (w.tok m r) (w.outTok m resp)] }
  | .tool x t e, s =>
      { s with store := upd s.store x (w.toolFn t (evalE s.store e)),
               trace := s.trace ++ [.tool t] }
  | .dummy m T N, s => { s with trace := s.trace ++ [dummyEvent w m T N] }
  | .dummyTool t, s => { s with trace := s.trace ++ [.tool t] }
  | .ite g a b, s => if holds s.store g then exec w ω a s else exec w ω b s
  | .loop n g body padded, s =>
      loopRun (exec w ω body) (ghost w ((shape body).getD [])) g padded n s

def labelE (Γ : Ctx) : Expr → Label
  | .lit _ => .low
  | .var x => Γ x
  | .app a b => (labelE Γ a).join (labelE Γ b)
  | .escape e => labelE Γ e
  | .trim e => labelE Γ e

/-- The padding discipline checked on compiler output. -/
def wt (Γ : Ctx) : Label → Stmt → Bool
  | _, .skip => true
  | pc, .seq a b => wt Γ pc a && wt Γ pc b
  | pc, .call _ x _ _ e p =>
      (pc.join (labelE Γ e)).le (Γ x) && (pc.join (labelE Γ e) == .low || p.isSome)
  | pc, .tool x _ e => (pc.join (labelE Γ e)).le (Γ x)
  | _, .dummy .. => true
  | _, .dummyTool _ => true
  | pc, .ite g a b =>
      wt Γ (pc.join (Γ (guardVar g))) a && wt Γ (pc.join (Γ (guardVar g))) b &&
      (pc.join (Γ (guardVar g)) == .low || (shape (.ite g a b)).isSome)
  | pc, .loop _ g body padded =>
      wt Γ (pc.join (Γ (guardVar g))) body &&
      (pc.join (Γ (guardVar g)) == .low || (padded && (shape body).isSome))

/-- Randomness-cell discipline: call sites reached under a high program counter
    are exactly those marked by `H`. -/
def sitesOK (Γ : Ctx) (H : Nat → Bool) : Label → Stmt → Bool
  | pc, .seq a b => sitesOK Γ H pc a && sitesOK Γ H pc b
  | pc, .call i _ _ _ _ _ => H i == (pc == .high)
  | pc, .ite g a b =>
      sitesOK Γ H (pc.join (Γ (guardVar g))) a && sitesOK Γ H (pc.join (Γ (guardVar g))) b
  | pc, .loop _ g body _ => sitesOK Γ H (pc.join (Γ (guardVar g))) body
  | _, _ => true

def lowEq (Γ : Ctx) (σ τ : Store) : Prop := ∀ x, Γ x = .low → σ x = τ x
def agreeOff (H : Nat → Bool) (c d : Nat → Nat) : Prop := ∀ i, H i = false → c i = d i

/-! ### Basic lemmas -/

theorem join_low_iff (a b : Label) : a.join b = .low ↔ a = .low ∧ b = .low := by
  cases a <;> cases b <;> simp [Label.join]

theorem le_high_right (l : Label) (h : Label.le .high l = true) : l = .high := by
  cases l <;> simp_all [Label.le]

theorem evalE_low (Γ : Ctx) (σ τ : Store) (h : lowEq Γ σ τ) :
    ∀ e, labelE Γ e = .low → evalE σ e = evalE τ e := by
  intro e
  induction e with
  | lit s => intro _; rfl
  | var x => intro hx; exact h x hx
  | app a b iha ihb =>
      intro hl
      have := (join_low_iff _ _).mp hl
      simp [evalE, iha this.1, ihb this.2]
  | escape e ih =>
      intro hl
      simp [evalE, ih hl]
  | trim e ih =>
      intro hl
      simp [evalE, ih hl]

theorem holds_low (Γ : Ctx) (σ τ : Store) (h : lowEq Γ σ τ) (g : Guard)
    (hg : Γ (guardVar g) = .low) : holds σ g = holds τ g := by
  cases g <;> simp [holds, guardVar] at * <;> rw [h _ hg]

theorem iter_store (f : St → St) (hf : ∀ s, (f s).store = s.store) :
    ∀ n s, (iter f n s).store = s.store := by
  intro n
  induction n with
  | zero => intro s; rfl
  | succ n ih => intro s; simp [iter, ih, hf]

theorem iter_count (f : St → St) (hf : ∀ s, (f s).count = s.count) :
    ∀ n s, (iter f n s).count = s.count := by
  intro n
  induction n with
  | zero => intro s; rfl
  | succ n ih => intro s; simp [iter, ih, hf]

theorem rep_comm (n : Nat) (x : List Event) : x ++ rep n x = rep n x ++ x := by
  induction n with
  | zero => simp [rep]
  | succ n ih =>
      show x ++ (x ++ rep n x) = (x ++ rep n x) ++ x
      conv => lhs; rw [ih]
      simp

theorem rep_succ' (n : Nat) (x : List Event) : rep (n+1) x = rep n x ++ x := by
  show x ++ rep n x = _
  exact rep_comm n x

theorem iter_trace (f : St → St) (x : List Event) (hf : ∀ s, (f s).trace = s.trace ++ x) :
    ∀ n s, (iter f n s).trace = s.trace ++ rep n x := by
  intro n
  induction n with
  | zero => intro s; simp [iter, rep]
  | succ n ih =>
      intro s; simp [iter, ih, hf, rep_succ']
      try exact rep_comm n x

theorem ghost_map (w : World) (hw : w.Conforms) (x : List Event) :
    x.map (ghostEvent w) = x := by
  induction x with
  | nil => rfl
  | cons e t ih =>
      cases e <;> simp [ghostEvent, dummyEvent, hw.1, hw.2, ih]

/-! ### Shape lemma: a statement with a static shape emits exactly that shape -/

theorem loopRun_trace (step ghostStep : St → St) (g : Guard) (x : List Event)
    (hs : ∀ s, (step s).trace = s.trace ++ x) (hg : ∀ s, (ghostStep s).trace = s.trace ++ x) :
    ∀ n s, (loopRun step ghostStep g true n s).trace = s.trace ++ rep n x := by
  intro n
  induction n with
  | zero => intro s; simp [loopRun, rep]
  | succ n ih =>
      intro s
      by_cases hh : holds s.store g = true
      · simp [loopRun, hh, iter_trace ghostStep x hg]
      · simp [loopRun, hh, ih, hs, rep_succ', rep]

theorem shape_exec (w : World) (hw : w.Conforms) (ω : Nat → Nat → Nat) :
    ∀ (s : Stmt) (sh : List Event), shape s = some sh →
      ∀ st, (exec w ω s st).trace = st.trace ++ sh := by
  intro s
  induction s with
  | skip => intro sh h st; simp [shape] at h; subst h; simp [exec]
  | seq a b iha ihb =>
      intro sh h st
      cases ha : shape a with
      | none => simp [shape, ha] at h
      | some x =>
          cases hb : shape b with
          | none => simp [shape, ha, hb] at h
          | some y =>
              simp [shape, ha, hb] at h; subst h
              simp [exec, ihb y hb, iha x ha]
  | call i x m k e p =>
      intro sh h st
      cases p with
      | none => simp [shape] at h
      | some tn =>
          obtain ⟨T, N⟩ := tn
          simp [shape] at h; subst h
          simp [exec, hw.1, hw.2]
  | tool x t e => intro sh h st; simp [shape] at h; subst h; simp [exec]
  | dummy m T N => intro sh h st; simp [shape] at h; subst h; simp [exec, dummyEvent, hw.1, hw.2]
  | dummyTool t => intro sh h st; simp [shape] at h; subst h; simp [exec]
  | ite g a b iha ihb =>
      intro sh h st
      cases ha : shape a with
      | none => simp [shape, ha] at h
      | some x =>
          cases hb : shape b with
          | none => simp [shape, ha, hb] at h
          | some y =>
              by_cases hxy : x = y
              · subst hxy
                simp [shape, ha, hb] at h; subst h
                by_cases hh : holds st.store g = true
                · simp [exec, hh, iha _ ha]
                · simp [exec, hh, ihb _ hb]
              · simp [shape, ha, hb, hxy] at h
  | loop n g body padded ih =>
      intro sh h st
      cases padded with
      | false => simp [shape] at h
      | true =>
          cases hb : shape body with
          | none => simp [shape, hb] at h
          | some x =>
              simp [shape, hb] at h; subst h
              simp only [exec, hb, Option.getD]
              apply loopRun_trace
              · exact ih x hb
              · intro s; simp [ghost, ghost_map w hw]

/-! ### Contract-indexed accounting of a complete shape

No token counts from different model contracts are added together. This is a
logical usage theorem, not a currency, latency or provider billing theorem. A
checked whole-workflow shape permits admission before any secret is evaluated.
The dynamic reservation ledger additionally detects unsupported executions. -/

def usage (model : String) : List Event → Nat × Nat × Nat
  | [] => (0, 0, 0)
  | .tool _ :: tail => usage model tail
  | .llm m i o :: tail =>
      let (ti, to, tc) := usage model tail
      if m = model then (i + ti, o + to, 1 + tc) else (ti, to, tc)

def Within (actual limit : Nat × Nat × Nat) : Prop :=
  actual.1 ≤ limit.1 ∧ actual.2.1 ≤ limit.2.1 ∧ actual.2.2 ≤ limit.2.2

theorem shape_usage_exact (w : World) (hw : w.Conforms) (ω : Nat → Nat → Nat)
    (p : Stmt) (sh : List Event) (hs : shape p = some sh) (σ : Store) (m : String) :
    usage m (exec w ω p ⟨σ, fun _ => 0, []⟩).trace = usage m sh := by
  rw [shape_exec w hw ω p sh hs]
  rfl

theorem shape_budget_sound (w : World) (hw : w.Conforms) (ω : Nat → Nat → Nat)
    (p : Stmt) (sh : List Event) (hs : shape p = some sh) (σ : Store)
    (budget : String → Nat × Nat × Nat) (hb : ∀ m, Within (usage m sh) (budget m)) :
    ∀ m, Within (usage m (exec w ω p ⟨σ, fun _ => 0, []⟩).trace) (budget m) := by
  intro m
  rw [shape_usage_exact w hw ω p sh hs]
  exact hb m

/-! ### Confinement: high-context statements write no low variable and read
    no low randomness cell -/

theorem loopRun_store (step ghostStep : St → St) (g : Guard) (padded : Bool) (P : Store → Prop)
    (hs : ∀ s, P s.store → P (step s).store) (hg : ∀ s, (ghostStep s).store = s.store) :
    ∀ n s, P s.store → P (loopRun step ghostStep g padded n s).store := by
  intro n
  induction n with
  | zero => intro s h; simpa [loopRun] using h
  | succ n ih =>
      intro s h
      by_cases hh : holds s.store g = true
      · cases padded <;> simp [loopRun, hh, iter_store ghostStep hg, h]
      · simp [loopRun, hh]; exact ih _ (hs s h)

theorem loopRun_count (step ghostStep : St → St) (g : Guard) (padded : Bool) (P : (Nat → Nat) → Prop)
    (hs : ∀ s, P s.count → P (step s).count) (hg : ∀ s, (ghostStep s).count = s.count) :
    ∀ n s, P s.count → P (loopRun step ghostStep g padded n s).count := by
  intro n
  induction n with
  | zero => intro s h; simpa [loopRun] using h
  | succ n ih =>
      intro s h
      by_cases hh : holds s.store g = true
      · cases padded <;> simp [loopRun, hh, iter_count ghostStep hg, h]
      · simp [loopRun, hh]; exact ih _ (hs s h)

theorem high_store (w : World) (ω : Nat → Nat → Nat) (Γ : Ctx) :
    ∀ (s : Stmt), wt Γ .high s = true →
      ∀ st, lowEq Γ st.store (exec w ω s st).store := by
  intro s
  induction s with
  | skip => intro _ st x _; rfl
  | seq a b iha ihb =>
      intro h st x hx
      simp [wt] at h
      simp only [exec]
      rw [iha h.1 st x hx]; exact ihb h.2 _ x hx
  | call i y m k e p =>
      intro h st x hx
      simp [wt, Label.join] at h
      have hy := le_high_right _ h.1
      have hne : x ≠ y := by intro hxy; subst hxy; rw [hx] at hy; cases hy
      cases p with
      | none => simp [exec, upd, hne]
      | some tn => obtain ⟨T, N⟩ := tn; simp [exec, upd, hne]
  | tool y t e =>
      intro h st x hx
      simp [wt, Label.join] at h
      have hy := le_high_right _ h
      have hne : x ≠ y := by intro hxy; subst hxy; rw [hx] at hy; cases hy
      simp [exec, upd, hne]
  | dummy => intro _ st x _; rfl
  | dummyTool => intro _ st x _; rfl
  | ite g a b iha ihb =>
      intro h st x hx
      simp [wt, Label.join] at h
      by_cases hh : holds st.store g = true
      · simp [exec, hh]; exact iha h.1.1 st x hx
      · simp [exec, hh]; exact ihb h.1.2 st x hx
  | loop n g body padded ih =>
      intro h st
      simp [wt, Label.join] at h
      simp only [exec]
      apply loopRun_store (P := fun σ => lowEq Γ st.store σ)
      · intro s hs x hx; rw [hs x hx]; exact ih h.1 s x hx
      · intro s; rfl
      · intro x _; rfl

theorem bump_off (c : Nat → Nat) (i j : Nat) (h : j ≠ i) : bump c i j = c j := by
  simp [bump, h]

theorem high_count (w : World) (ω : Nat → Nat → Nat) (Γ : Ctx) (H : Nat → Bool) :
    ∀ (s : Stmt), sitesOK Γ H .high s = true →
      ∀ st j, H j = false → (exec w ω s st).count j = st.count j := by
  intro s
  induction s with
  | skip => intro _ st j _; rfl
  | seq a b iha ihb =>
      intro h st j hj
      simp [sitesOK] at h
      simp only [exec]
      rw [ihb h.2 _ j hj, iha h.1 st j hj]
  | call i y m k e p =>
      intro h st j hj
      simp [sitesOK] at h
      have hne : j ≠ i := by intro hji; subst hji; rw [hj] at h; cases h
      cases p with
      | none => simp [exec, bump, hne]
      | some tn => obtain ⟨T, N⟩ := tn; simp [exec, bump, hne]
  | tool => intro _ st j _; rfl
  | dummy => intro _ st j _; rfl
  | dummyTool => intro _ st j _; rfl
  | ite g a b iha ihb =>
      intro h st j hj
      simp [sitesOK, Label.join] at h
      by_cases hh : holds st.store g = true
      · simp [exec, hh]; exact iha h.1 st j hj
      · simp [exec, hh]; exact ihb h.2 st j hj
  | loop n g body padded ih =>
      intro h st j hj
      simp [sitesOK, Label.join] at h
      simp only [exec]
      apply loopRun_count (P := fun c => c j = st.count j)
      · intro s hs; rw [ih h s j hj]; exact hs
      · intro s; rfl
      · rfl

/-! ### Main theorem: usage-trace noninterference -/

theorem loopRun_low (step1 step2 ghostStep : St → St) (g : Guard) (padded : Bool) (R : St → St → Prop)
    (hstep : ∀ a b, R a b → R (step1 a) (step2 b))
    (hghost : ∀ a b, R a b → R (ghostStep a) (ghostStep b))
    (hguard : ∀ a b, R a b → holds a.store g = holds b.store g) :
    ∀ n a b, R a b → R (loopRun step1 ghostStep g padded n a) (loopRun step2 ghostStep g padded n b) := by
  have hiter : ∀ m a b, R a b → R (iter ghostStep m a) (iter ghostStep m b) := by
    intro m
    induction m with
    | zero => intro a b h; exact h
    | succ m ih => intro a b h; exact ih _ _ (hghost a b h)
  intro n
  induction n with
  | zero => intro a b h; simpa [loopRun] using h
  | succ n ih =>
      intro a b h
      have hg := hguard a b h
      by_cases hh : holds a.store g = true
      · have hb : holds b.store g = true := by rw [← hg]; exact hh
        cases padded
        · simp [loopRun, hh, hb]; exact h
        · simp [loopRun, hh, hb]; exact hiter _ _ _ h
      · have hb : ¬ holds b.store g = true := by rw [← hg]; exact hh
        simp [loopRun, hh, hb]
        exact ih _ _ (hstep a b h)

/-- Low-equivalence of two states for the observer. -/
def related (Γ : Ctx) (H : Nat → Bool) (a b : St) : Prop :=
  lowEq Γ a.store b.store ∧ agreeOff H a.count b.count ∧ a.trace = b.trace

theorem noninterference (w : World) (hw : w.Conforms) (ω : Nat → Nat → Nat)
    (Γ : Ctx) (H : Nat → Bool) :
    ∀ (s : Stmt), wt Γ .low s = true → sitesOK Γ H .low s = true →
      ∀ a b, related Γ H a b → related Γ H (exec w ω s a) (exec w ω s b) := by
  intro s
  induction s with
  | skip => intro _ _ a b h; exact h
  | seq x y ihx ihy =>
      intro hwt hs a b h
      simp [wt] at hwt; simp [sitesOK] at hs
      exact ihy hwt.2 hs.2 _ _ (ihx hwt.1 hs.1 a b h)
  | call i x m k e p =>
      intro hwt hs a b h
      obtain ⟨hl, hc, ht⟩ := h
      simp [sitesOK] at hs
      have hci : a.count i = b.count i := hc i (by simpa using hs)
      have hbump : agreeOff H (bump a.count i) (bump b.count i) := by
        intro j hj
        by_cases hji : j = i
        · subst hji; simp [bump, hci]
        · simp [bump, hji]; exact hc j hj
      cases hlab : labelE Γ e with
      | low =>
          have hr := evalE_low Γ _ _ hl e hlab
          cases p with
          | none =>
              refine ⟨?_, hbump, ?_⟩
              · intro z hz; simp [exec, upd]; split
                · rw [hr, hci]
                · exact hl z hz
              · simp [exec, ht, hr, hci]
          | some tn =>
              obtain ⟨T, N⟩ := tn
              refine ⟨?_, hbump, ?_⟩
              · intro z hz; simp [exec, upd]; split
                · rw [hr, hci]
                · exact hl z hz
              · simp [exec, ht, hw.1, hw.2]
      | high =>
          simp [wt, Label.join, hlab] at hwt
          have hx := le_high_right _ hwt.1
          cases p with
          | none => simp at hwt
          | some tn =>
              obtain ⟨T, N⟩ := tn
              refine ⟨?_, hbump, ?_⟩
              · intro z hz
                have hne : z ≠ x := by intro hzx; subst hzx; rw [hz] at hx; cases hx
                simp [exec, upd, hne]; exact hl z hz
              · simp [exec, ht, hw.1, hw.2]
  | tool x t e =>
      intro hwt _ a b h
      obtain ⟨hl, hc, ht⟩ := h
      refine ⟨?_, hc, ?_⟩
      · intro z hz
        simp [exec, upd]
        split
        · rename_i hzx; subst hzx
          cases hlab : labelE Γ e with
          | low => rw [evalE_low Γ _ _ hl e hlab]
          | high =>
              simp [wt, Label.join, hlab] at hwt
              have := le_high_right _ hwt; rw [hz] at this; cases this
        · exact hl z hz
      · simp [exec, ht]
  | dummy m T N =>
      intro _ _ a b h
      obtain ⟨hl, hc, ht⟩ := h
      exact ⟨hl, hc, by simp [exec, ht]⟩
  | dummyTool t =>
      intro _ _ a b h
      obtain ⟨hl, hc, ht⟩ := h
      exact ⟨hl, hc, by simp [exec, ht]⟩
  | ite g x y ihx ihy =>
      intro hwt hs a b h
      cases hgl : Γ (guardVar g) with
      | low =>
          simp [wt, sitesOK, Label.join, hgl] at hwt hs
          have hg := holds_low Γ _ _ h.1 g hgl
          by_cases hh : holds a.store g = true
          · have hb : holds b.store g = true := by rw [← hg]; exact hh
            simp [exec, hh, hb]; exact ihx hwt.1 hs.1 a b h
          · have hb : ¬ holds b.store g = true := by rw [← hg]; exact hh
            simp [exec, hh, hb]; exact ihy hwt.2 hs.2 a b h
      | high =>
          have hwt' := hwt
          simp [wt, sitesOK, Label.join, hgl] at hwt hs
          obtain ⟨⟨hwx, hwy⟩, hsh⟩ := hwt
          obtain ⟨sh, hsheq⟩ := Option.isSome_iff_exists.mp hsh
          have htr : ∀ st, (exec w ω (.ite g x y) st).trace = st.trace ++ sh :=
            shape_exec w hw ω _ sh hsheq
          have hstore : ∀ st, lowEq Γ st.store (exec w ω (.ite g x y) st).store := by
            intro st z hz
            by_cases hh : holds st.store g = true
            · simp [exec, hh]; exact high_store w ω Γ x hwx st z hz
            · simp [exec, hh]; exact high_store w ω Γ y hwy st z hz
          have hcount : ∀ st j, H j = false → (exec w ω (.ite g x y) st).count j = st.count j := by
            intro st j hj
            by_cases hh : holds st.store g = true
            · simp [exec, hh]; exact high_count w ω Γ H x hs.1 st j hj
            · simp [exec, hh]; exact high_count w ω Γ H y hs.2 st j hj
          obtain ⟨hl, hc, ht⟩ := h
          refine ⟨?_, ?_, ?_⟩
          · intro z hz; rw [← hstore a z hz, ← hstore b z hz]; exact hl z hz
          · intro j hj; rw [hcount a j hj, hcount b j hj]; exact hc j hj
          · rw [htr a, htr b, ht]
  | loop n g body padded ih =>
      intro hwt hs a b h
      cases hgl : Γ (guardVar g) with
      | low =>
          simp [wt, sitesOK, Label.join, hgl] at hwt hs
          simp only [exec]
          apply loopRun_low (R := related Γ H)
          · intro u v huv; exact ih hwt hs u v huv
          · intro u v huv
            obtain ⟨hl, hc, ht⟩ := huv
            exact ⟨hl, hc, by simp [ghost, ht]⟩
          · intro u v huv; exact holds_low Γ _ _ huv.1 g hgl
          · exact h
      | high =>
          simp [wt, sitesOK, Label.join, hgl] at hwt hs
          obtain ⟨hwb, hpad, hsh⟩ := hwt
          subst hpad
          obtain ⟨x, hx⟩ := Option.isSome_iff_exists.mp hsh
          have hshape : shape (.loop n g body true) = some (rep n x) := by simp [shape, hx]
          have htr := shape_exec w hw ω _ _ hshape
          have hstore : ∀ st, lowEq Γ st.store (exec w ω (.loop n g body true) st).store := by
            intro st
            simp only [exec]
            apply loopRun_store (P := fun σ => lowEq Γ st.store σ)
            · intro s hs z hz; rw [hs z hz]; exact high_store w ω Γ body hwb s z hz
            · intro s; rfl
            · intro z _; rfl
          have hcount : ∀ st j, H j = false → (exec w ω (.loop n g body true) st).count j = st.count j := by
            intro st j hj
            simp only [exec]
            apply loopRun_count (P := fun c => c j = st.count j)
            · intro s hs'; rw [high_count w ω Γ H body hs s j hj]; exact hs'
            · intro s; rfl
            · rfl
          obtain ⟨hl, hc, ht⟩ := h
          refine ⟨?_, ?_, ?_⟩
          · intro z hz; rw [← hstore a z hz, ← hstore b z hz]; exact hl z hz
          · intro j hj; rw [hcount a j hj, hcount b j hj]; exact hc j hj
          · rw [htr a, htr b, ht]

/-- Initial states that differ only in high variables yield identical usage
    traces for every randomness tape. -/
theorem trace_noninterference (w : World) (hw : w.Conforms) (Γ : Ctx) (H : Nat → Bool)
    (s : Stmt) (hwt : wt Γ .low s = true) (hs : sitesOK Γ H .low s = true)
    (σ τ : Store) (hlow : lowEq Γ σ τ) (ω : Nat → Nat → Nat) :
    (exec w ω s ⟨σ, fun _ => 0, []⟩).trace = (exec w ω s ⟨τ, fun _ => 0, []⟩).trace :=
  (noninterference w hw ω Γ H s hwt hs ⟨σ, fun _ => 0, []⟩ ⟨τ, fun _ => 0, []⟩
    ⟨hlow, fun _ _ => rfl, rfl⟩).2.2

/-- Distributional form: for any finite weighted family of tapes, the induced
    weighted trace lists coincide. -/
theorem distribution_noninterference {W : Type} (w : World) (hw : w.Conforms) (Γ : Ctx)
    (H : Nat → Bool) (s : Stmt) (hwt : wt Γ .low s = true) (hs : sitesOK Γ H .low s = true)
    (σ τ : Store) (hlow : lowEq Γ σ τ) (μ : List (W × (Nat → Nat → Nat))) :
    μ.map (fun p => (p.1, (exec w p.2 s ⟨σ, fun _ => 0, []⟩).trace)) =
    μ.map (fun p => (p.1, (exec w p.2 s ⟨τ, fun _ => 0, []⟩).trace)) := by
  apply List.map_congr_left
  intro p _
  rw [trace_noninterference w hw Γ H s hwt hs σ τ hlow p.2]

/-! ### Functional preservation of the padding transformation -/

theorem loopRun_rel2 (s1 s2 g1 g2 : St → St) (g : Guard) (p1 p2 : Bool) (R : St → St → Prop)
    (hs : ∀ a b, R a b → R (s1 a) (s2 b))
    (hg1 : ∀ a b, R a b → R (g1 a) b) (hg2 : ∀ a b, R a b → R a (g2 b))
    (hguard : ∀ a b, R a b → holds a.store g = holds b.store g) :
    ∀ n a b, R a b → R (loopRun s1 g1 g p1 n a) (loopRun s2 g2 g p2 n b) := by
  have i1 : ∀ m a b, R a b → R (iter g1 m a) b := by
    intro m; induction m with
    | zero => intro a b h; exact h
    | succ m ih => intro a b h; exact ih _ _ (hg1 a b h)
  have i2 : ∀ m a b, R a b → R a (iter g2 m b) := by
    intro m; induction m with
    | zero => intro a b h; exact h
    | succ m ih => intro a b h; exact ih _ _ (hg2 a b h)
  intro n
  induction n with
  | zero => intro a b h; simpa [loopRun] using h
  | succ n ih =>
      intro a b h
      have hg := hguard a b h
      by_cases hh : holds a.store g = true
      · have hb : holds b.store g = true := by rw [← hg]; exact hh
        cases p1 <;> cases p2 <;> simp [loopRun, hh, hb] <;>
          first | exact h | exact i1 _ _ _ h | exact i2 _ _ _ h | exact i1 _ _ _ (i2 _ _ _ h)
      · have hb : ¬ holds b.store g = true := by rw [← hg]; exact hh
        simp [loopRun, hh, hb]
        exact ih _ _ (hs a b h)

/-- Forced lengths never undercut a call's own visible cap. -/
def capsOK : Stmt → Bool
  | .seq a b => capsOK a && capsOK b
  | .call _ _ _ k _ (some (_, N)) => decide (k ≤ N)
  | .ite _ a b => capsOK a && capsOK b
  | .loop _ _ body _ => capsOK body
  | _ => true

/-- Remove everything the shaping compiler may add. -/
def erase : Stmt → Stmt
  | .skip => .skip
  | .seq a b => .seq (erase a) (erase b)
  | .call i x m k e _ => .call i x m k e none
  | .tool x t e => .tool x t e
  | .dummy .. => .skip
  | .dummyTool _ => .skip
  | .ite g a b => .ite g (erase a) (erase b)
  | .loop n g body _ => .loop n g (erase body) false

def sameData (a b : St) : Prop := a.store = b.store ∧ a.count = b.count

theorem erase_correct (w : World) (ht : w.Transparent) (ω : Nat → Nat → Nat) :
    ∀ (s : Stmt), capsOK s = true →
      ∀ a b, sameData a b → sameData (exec w ω s a) (exec w ω (erase s) b) := by
  unfold World.Transparent at ht
  intro s
  induction s with
  | skip => intro _ a b h; exact h
  | seq x y ihx ihy =>
      intro hc a b h
      simp [capsOK] at hc
      exact ihy hc.2 _ _ (ihx hc.1 a b h)
  | call i x m k e p =>
      intro hk a b h
      obtain ⟨hs, hc⟩ := h
      cases p with
      | none => simp [erase, exec, sameData, hs, hc]
      | some tn =>
          obtain ⟨T, N⟩ := tn
          simp [capsOK] at hk
          simp [erase, exec, sameData, hs, hc, ht m k T N _ _ hk]
  | tool x t e => intro _ a b h; obtain ⟨hs, hc⟩ := h; simp [erase, exec, sameData, hs, hc]
  | dummy => intro _ a b h; exact h
  | dummyTool => intro _ a b h; exact h
  | ite g x y ihx ihy =>
      intro hc a b h
      simp [capsOK] at hc
      have hg : holds a.store g = holds b.store g := by rw [h.1]
      by_cases hh : holds a.store g = true
      · have hb : holds b.store g = true := by rw [← hg]; exact hh
        simp [erase, exec, hh, hb]; exact ihx hc.1 a b h
      · have hb : ¬ holds b.store g = true := by rw [← hg]; exact hh
        simp [erase, exec, hh, hb]; exact ihy hc.2 a b h
  | loop n g body padded ih =>
      intro hc a b h
      simp [capsOK] at hc
      simp only [erase, exec]
      apply loopRun_rel2 (R := sameData)
      · exact ih hc
      · intro u v huv; exact huv
      · intro u v huv; exact huv
      · intro u v huv; rw [huv.1]
      · exact h

/-! ### Normalization of `skip` in erased programs -/

def build : List Stmt → Stmt
  | [] => .skip
  | [x] => x
  | x :: xs => .seq x (build xs)

/-- Flatten sequences (associativity), drop `skip`, recursively. -/
def items : Stmt → List Stmt
  | .seq a b => items a ++ items b
  | .skip => []
  | .ite g a b => [.ite g (build (items a)) (build (items b))]
  | .loop n g body p => [.loop n g (build (items body)) p]
  | s => [s]

def clean (s : Stmt) : Stmt := build (items s)

def execList (w : World) (ω : Nat → Nat → Nat) : List Stmt → St → St
  | [], st => st
  | x :: xs, st => execList w ω xs (exec w ω x st)

theorem build_exec (w : World) (ω : Nat → Nat → Nat) :
    ∀ l st, exec w ω (build l) st = execList w ω l st := by
  intro l
  induction l with
  | nil => intro st; rfl
  | cons x xs ih =>
      intro st
      cases xs with
      | nil => rfl
      | cons y ys => simp only [build, exec, execList]; rw [ih]; rfl

theorem execList_append (w : World) (ω : Nat → Nat → Nat) :
    ∀ l1 l2 st, execList w ω (l1 ++ l2) st = execList w ω l2 (execList w ω l1 st) := by
  intro l1
  induction l1 with
  | nil => intro l2 st; rfl
  | cons x xs ih => intro l2 st; simp only [List.cons_append, execList]; rw [ih]

theorem clean_data (w : World) (ω : Nat → Nat → Nat) :
    ∀ (s : Stmt) a b, sameData a b → sameData (exec w ω s a) (exec w ω (clean s) b) := by
  have key : ∀ (s : Stmt) a b, sameData a b → sameData (exec w ω s a) (execList w ω (items s) b) := by
    intro s
    induction s with
    | seq x y ihx ihy =>
        intro a b h
        simp only [items, exec]
        rw [execList_append]
        exact ihy _ _ (ihx a b h)
    | skip => intro a b h; exact h
    | ite g x y ihx ihy =>
        intro a b h
        simp only [items, execList]
        have hg : holds a.store g = holds b.store g := by rw [h.1]
        by_cases hh : holds a.store g = true
        · have hb : holds b.store g = true := by rw [← hg]; exact hh
          simp [exec, hh, hb, build_exec]; exact ihx a b h
        · have hb : ¬ holds b.store g = true := by rw [← hg]; exact hh
          simp [exec, hh, hb, build_exec]; exact ihy a b h
    | loop n g body p ih =>
        intro a b h
        simp only [items, execList, exec]
        have hb : exec w ω (build (items body)) = execList w ω (items body) := by
          funext st; exact build_exec w ω _ st
        rw [hb]
        apply loopRun_rel2 (R := sameData)
        · exact ih
        · intro u v huv; exact huv
        · intro u v huv; exact huv
        · intro u v huv; rw [huv.1]
        · exact h
    | call i x m k e p =>
        intro a b h; obtain ⟨hs, hc⟩ := h
        cases p with
        | none => simp [items, execList, exec, sameData, hs, hc]
        | some tn => obtain ⟨T, N⟩ := tn; simp [items, execList, exec, sameData, hs, hc]
    | tool x t e => intro a b h; obtain ⟨hs, hc⟩ := h; simp [items, execList, exec, sameData, hs, hc]
    | dummy => intro a b h; exact h
    | dummyTool => intro a b h; exact h
  intro s a b h
  simp only [clean]
  rw [build_exec]
  exact key s a b h

/-! ### Executable translation validator -/

/-- Accept compiler output `padded` for source `orig` when padding only added
    annotations/dummies and the padding discipline holds. -/
def validate (Γ : Ctx) (H : Nat → Bool) (orig padded : Stmt) : Bool :=
  clean (erase padded) == clean (erase orig) && wt Γ .low padded && sitesOK Γ H .low padded &&
    capsOK padded

theorem validate_sound (w : World) (hw : w.Conforms) (Γ : Ctx) (H : Nat → Bool)
    (orig padded : Stmt) (hv : validate Γ H orig padded = true) :
    (∀ σ τ ω, lowEq Γ σ τ →
      (exec w ω padded ⟨σ, fun _ => 0, []⟩).trace = (exec w ω padded ⟨τ, fun _ => 0, []⟩).trace) ∧
    (w.Transparent → ∀ σ ω,
      (exec w ω padded ⟨σ, fun _ => 0, []⟩).store = (exec w ω (erase orig) ⟨σ, fun _ => 0, []⟩).store) := by
  simp [validate] at hv
  obtain ⟨⟨⟨he, hwt⟩, hs⟩, hcap⟩ := hv
  refine ⟨fun σ τ ω hl => trace_noninterference w hw Γ H padded hwt hs σ τ hl ω, ?_⟩
  intro ht σ ω
  let st : St := ⟨σ, fun _ => 0, []⟩
  have h1 := erase_correct w ht ω padded hcap st st ⟨rfl, rfl⟩
  have h2 := clean_data w ω (erase padded) st st ⟨rfl, rfl⟩
  have h3 := clean_data w ω (erase orig) st st ⟨rfl, rfl⟩
  rw [he] at h2
  exact h1.1.trans (h2.1.trans h3.1.symm)

/-- Sites reached under a high program counter; the executable validator
    derives `H` from the candidate program and then checks `sitesOK`. -/
def highSites (Γ : Ctx) : Label → Stmt → List Nat
  | pc, .seq a b => highSites Γ pc a ++ highSites Γ pc b
  | pc, .call i _ _ _ _ _ => if pc == .high then [i] else []
  | pc, .ite g a b =>
      highSites Γ (pc.join (Γ (guardVar g))) a ++ highSites Γ (pc.join (Γ (guardVar g))) b
  | pc, .loop _ g body _ => highSites Γ (pc.join (Γ (guardVar g))) body
  | _, _ => []

def validateProgram (Γ : Ctx) (orig padded : Stmt) : Bool :=
  validate Γ (fun i => (highSites Γ .low padded).contains i) orig padded

theorem validateProgram_sound (w : World) (hw : w.Conforms) (Γ : Ctx) (orig padded : Stmt)
    (hv : validateProgram Γ orig padded = true) :
    (∀ σ τ ω, lowEq Γ σ τ →
      (exec w ω padded ⟨σ, fun _ => 0, []⟩).trace = (exec w ω padded ⟨τ, fun _ => 0, []⟩).trace) ∧
    (w.Transparent → ∀ σ ω,
      (exec w ω padded ⟨σ, fun _ => 0, []⟩).store = (exec w ω (erase orig) ⟨σ, fun _ => 0, []⟩).store) :=
  validate_sound w hw Γ _ orig padded hv

/-- End-to-end form: if every declared secret input is labelled high, runs from
    stores that differ only in declared secret inputs emit identical traces. -/
theorem secret_inputs_sound (w : World) (hw : w.Conforms) (Γ : Ctx) (orig padded : Stmt)
    (secrets : List Var) (hs : ∀ x, x ∈ secrets → Γ x = .high)
    (hv : validateProgram Γ orig padded = true) (σ τ : Store)
    (hdiff : ∀ x, x ∉ secrets → σ x = τ x) (ω : Nat → Nat → Nat) :
    (exec w ω padded ⟨σ, fun _ => 0, []⟩).trace = (exec w ω padded ⟨τ, fun _ => 0, []⟩).trace := by
  apply (validateProgram_sound w hw Γ orig padded hv).1
  intro x hx
  apply hdiff x
  intro hmem
  rw [hs x hmem] at hx
  cases hx

-- A secret router whose arms make different calls is rejected until shaped.
private def Γex : Ctx := fun x => if x = 0 then .high else if x = 1 then .high else .low
private def leaky : Stmt :=
  .ite (.eq 0 "medical")
    (.call 1 1 "m" 32 (.app (.lit "Explain: ") (.var 0)) none)
    (.seq (.call 2 1 "m" 16 (.lit "Hello") none) (.call 3 1 "m" 32 (.var 1) none))
private def shaped : Stmt :=
  .ite (.eq 0 "medical")
    (.seq (.call 1 1 "m" 32 (.app (.lit "Explain: ") (.var 0)) (some (64, 32))) (.dummy "m" 64 32))
    (.seq (.call 2 1 "m" 16 (.lit "Hello") (some (64, 32))) (.call 3 1 "m" 32 (.var 1) (some (64, 32))))
#guard !validateProgram Γex leaky leaky
#guard validateProgram Γex leaky shaped
#guard !validateProgram Γex leaky (.ite (.eq 0 "medical") (.call 1 1 "m" 32 (.lit "x") (some (64, 32))) .skip)
#guard !validateProgram Γex (.call 1 2 "m" 8 (.var 0) none) (.call 1 2 "m" 8 (.var 0) (some (8, 8)))
#guard !validateProgram Γex leaky
  (.ite (.eq 0 "medical")
    (.seq (.call 1 1 "m" 32 (.app (.lit "Explain: ") (.var 0)) (some (64, 16))) (.dummy "m" 64 16))
    (.seq (.call 2 1 "m" 16 (.lit "Hello") (some (64, 16))) (.call 3 1 "m" 32 (.var 1) (some (64, 16)))))

#print axioms noninterference
#print axioms distribution_noninterference
#print axioms erase_correct
#print axioms validate_sound
#print axioms validateProgram_sound
#print axioms secret_inputs_sound
#print axioms shape_usage_exact
#print axioms shape_budget_sound

end OrchLang.Shape

namespace OrchLang.Shape
open Lean

private def arity (j : Json) (n : Nat) : Except String (Array Json) := do
  let a ← j.getArr?
  if a.size != n then throw s!"wrong constructor arity in {j.compress}"
  pure a

def decodeExpr : Nat → Json → Except String Expr
  | 0, _ => .error "expression nesting limit"
  | n+1, j => do
      let a ← j.getArr?
      match ← (← j.getArrVal? 0).getStr? with
      | "lit" => let _ ← arity j 2; pure (.lit (← a[1]!.getStr?))
      | "var" => let _ ← arity j 2; pure (.var (← a[1]!.getNat?))
      | "app" => let _ ← arity j 3; pure (.app (← decodeExpr n a[1]!) (← decodeExpr n a[2]!))
      | "escape" => let _ ← arity j 2; pure (.escape (← decodeExpr n a[1]!))
      | "trim" => let _ ← arity j 2; pure (.trim (← decodeExpr n a[1]!))
      | k => throw s!"unknown expression {k}"

def decodeGuard (j : Json) : Except String Guard := do
  let a ← arity j 3
  match ← a[0]!.getStr? with
  | "eq" => pure (.eq (← a[1]!.getNat?) (← a[2]!.getStr?))
  | "prefix" => pure (.prefix (← a[1]!.getNat?) (← a[2]!.getStr?))
  | k => throw s!"unknown guard {k}"

def decodeStmt : Nat → Json → Except String Stmt
  | 0, _ => .error "statement nesting limit"
  | n+1, j => do
      let a ← j.getArr?
      match ← (← j.getArrVal? 0).getStr? with
      | "skip" => let _ ← arity j 1; pure .skip
      | "seq" => let _ ← arity j 3; pure (.seq (← decodeStmt n a[1]!) (← decodeStmt n a[2]!))
      | "call" =>
          let _ ← arity j 7
          let pad ← match a[6]! with
            | .null => pure none
            | p => do
                let q ← arity p 2
                pure (some ((← q[0]!.getNat?), (← q[1]!.getNat?)))
          pure (.call (← a[1]!.getNat?) (← a[2]!.getNat?) (← a[3]!.getStr?) (← a[4]!.getNat?)
            (← decodeExpr 4096 a[5]!) pad)
      | "tool" =>
          let _ ← arity j 4
          pure (.tool (← a[1]!.getNat?) (← a[2]!.getStr?) (← decodeExpr 4096 a[3]!))
      | "dummy" =>
          let _ ← arity j 4
          pure (.dummy (← a[1]!.getStr?) (← a[2]!.getNat?) (← a[3]!.getNat?))
      | "dummyTool" => let _ ← arity j 2; pure (.dummyTool (← a[1]!.getStr?))
      | "ite" =>
          let _ ← arity j 4
          pure (.ite (← decodeGuard a[1]!) (← decodeStmt n a[2]!) (← decodeStmt n a[3]!))
      | "loop" =>
          let _ ← arity j 5
          pure (.loop (← a[1]!.getNat?) (← decodeGuard a[2]!) (← decodeStmt n a[3]!)
            (← a[4]!.getBool?))
      | k => throw s!"unknown statement {k}"

def encodeExpr : Expr → Json
  | .lit s => toJson ([toJson "lit", toJson s] : List Json)
  | .var x => toJson ([toJson "var", toJson x] : List Json)
  | .app a b => toJson ([toJson "app", encodeExpr a, encodeExpr b] : List Json)
  | .escape e => toJson ([toJson "escape", encodeExpr e] : List Json)
  | .trim e => toJson ([toJson "trim", encodeExpr e] : List Json)

def encodeGuard : Guard → Json
  | .eq x s => toJson ([toJson "eq", toJson x, toJson s] : List Json)
  | .prefix x s => toJson ([toJson "prefix", toJson x, toJson s] : List Json)

/-- Inverse of `decodeStmt`, used to check the serialization boundary. -/
def encodeStmt : Stmt → Json
  | .skip => toJson ([toJson "skip"] : List Json)
  | .seq a b => toJson ([toJson "seq", encodeStmt a, encodeStmt b] : List Json)
  | .call i x m k e p => toJson ([toJson "call", toJson i, toJson x, toJson m, toJson k, encodeExpr e,
      match p with
      | none => Json.null
      | some (T, N) => toJson ([toJson T, toJson N] : List Json)] : List Json)
  | .tool x t e => toJson ([toJson "tool", toJson x, toJson t, encodeExpr e] : List Json)
  | .dummy m T N => toJson ([toJson "dummy", toJson m, toJson T, toJson N] : List Json)
  | .dummyTool t => toJson ([toJson "dummyTool", toJson t] : List Json)
  | .ite g a b => toJson ([toJson "ite", encodeGuard g, encodeStmt a, encodeStmt b] : List Json)
  | .loop n g b p => toJson ([toJson "loop", toJson n, encodeGuard g, encodeStmt b, toJson p] : List Json)

def decodeCtx (j : Json) : Except String (List Var) := do
  (← j.getArr?).toList.mapM Json.getNat?

/-- Input: {"high": [vars], "original": stmt, "padded": stmt}. -/
def checkJson (j : Json) : Except String Json := do
  let high ← decodeCtx (← j.getObjVal? "high")
  let Γ : Ctx := fun x => if high.contains x then .high else .low
  let orig ← decodeStmt 4096 (← j.getObjVal? "original")
  let padded ← decodeStmt 4096 (← j.getObjVal? "padded")
  let secrets ← decodeCtx (← j.getObjVal? "secret_inputs")
  let secretsHigh := secrets.all high.contains
  let erased := clean (erase padded) == clean (erase orig)
  let typed := wt Γ .low padded
  let sites := sitesOK Γ (fun i => (highSites Γ .low padded).contains i) .low padded
  let shapeJson := match shape padded with
    | some sh => toJson (sh.map fun
        | .llm m i o => toJson ([toJson "llm", toJson m, toJson i, toJson o] : List Json)
        | .tool t => toJson ([toJson "tool", toJson t] : List Json))
    | none => Json.null
  pure (Json.mkObj [("accepted", Json.bool (validateProgram Γ orig padded && secretsHigh)),
    ("secrets_high", Json.bool secretsHigh),
    ("erasure_matches", Json.bool erased), ("padding_discipline", Json.bool typed),
    ("randomness_sites", Json.bool sites), ("caps", Json.bool (capsOK padded)),
    ("static_shape", shapeJson)])
end OrchLang.Shape

namespace OrchLang.Shape
open Lean

/- An explicit deterministic finite-table world used only for independent
   execution comparisons. These operations instantiate exec, not the theorem's
   provider hypothesis. No deployment or tokenizer theorem follows from them. -/
private def auditNat (s key : String) (fallback : Nat) : Nat :=
  match Json.parse s with
  | .ok j => (j.getObjValAs? Nat key).toOption.getD fallback
  | .error _ => fallback

private def auditText (s key : String) : String :=
  match Json.parse s with
  | .ok j => (j.getObjValAs? String key).toOption.getD s
  | .error _ => s

private def auditLookup (rows : List (String × String × String)) (model request : String) : String :=
  match rows.find? (fun r => r.1 == model && r.2.1 == request) with
  | some r => r.2.2
  | none => "missing"

private def auditWorld (rows : List (String × String × String)) : World :=
  { tok := fun _ r => auditNat r "__input_tokens" r.length
    gen := fun m r k _ => (auditLookup rows m r).take k
    forced := fun m r _ n =>
      (Json.mkObj [("__output_tokens",toJson n),
        ("__visible",toJson ((auditLookup rows m (auditText r "__request")).take n))]).compress
    view := fun _ k r => (auditText r "__visible").take k
    padReq := fun _ t r => (Json.mkObj [("__input_tokens",toJson t),("__request",toJson r)]).compress
    outTok := fun _ r => auditNat r "__output_tokens" r.length
    toolFn := fun t r => if t == "upper" then r.toUpper.take 6 else if t == "first" then r.take 1 else r
    dummyReq := "<user></>\n<a>" }

private def eventJson : Event → Json
  | .llm m i o => toJson ([toJson "llm",toJson m,toJson i,toJson o] : List Json)
  | .tool t => toJson ([toJson "tool",toJson t] : List Json)

def executeAuditJson (j : Json) : Except String Json := do
  let program ← decodeStmt 4096 (← j.getObjVal? "program")
  let slots ← (← (← j.getObjVal? "store").getArr?).toList.mapM fun row => do
    let a ← arity row 2
    pure ((← a[0]!.getNat?), (← a[1]!.getStr?))
  let rows ← (← (← j.getObjVal? "kernels").getArr?).toList.mapM fun row => do
    let a ← arity row 3
    pure ((← a[0]!.getStr?), (← a[1]!.getStr?), (← a[2]!.getStr?))
  let limit ← (← j.getObjVal? "store_limit").getNat?
  if limit > 64 then throw "store projection limit"
  let σ : Store := fun x => (slots.find? (fun p => p.1 == x)).map Prod.snd |>.getD ""
  let state := exec (auditWorld rows) (fun _ _ => 0) program ⟨σ,fun _ => 0,[]⟩
  pure (Json.mkObj [("trace",toJson (state.trace.map eventJson)),
    ("store",toJson ((List.range limit).map fun x => toJson ([toJson x,toJson (state.store x)] : List Json)))])

end OrchLang.Shape

def main (args : List String) : IO UInt32 := do
  match args with
  | ["roundtrip",path] =>
      let contents ← IO.FS.readFile path
      let result := do
        let j ← Lean.Json.parse contents
        let items ← j.getArr?
        pure (Lean.Json.arr (← items.mapM fun item => do
          pure (OrchLang.Shape.encodeStmt (← OrchLang.Shape.decodeStmt 4096 item))))
      match result with
      | .ok output => IO.println output.compress; pure 0
      | .error error => (← IO.getStderr).putStrLn error; pure 2
  | ["execute",path] =>
      let contents ← IO.FS.readFile path
      let result := do
        let j ← Lean.Json.parse contents
        let items ← j.getArr?
        pure (Lean.Json.arr (← items.mapM OrchLang.Shape.executeAuditJson))
      match result with
      | .ok output => IO.println output.compress; pure 0
      | .error error => (← IO.getStderr).putStrLn error; pure 2
  | [path] =>
      let contents ← IO.FS.readFile path
      let run (j : Lean.Json) : Except String Lean.Json :=
        match j with
        | .arr items => return Lean.Json.arr (← items.mapM OrchLang.Shape.checkJson)
        | _ => OrchLang.Shape.checkJson j
      match Lean.Json.parse contents >>= run with
      | .ok result =>
          IO.println result.compress
          let verdicts := match result with
            | .arr items => items.toList
            | j => [j]
          if verdicts.all (fun v => v.getObjValAs? Bool "accepted" matches .ok true) then pure 0 else pure 1
      | .error error => (← IO.getStderr).putStrLn error; pure 2
  | _ => (← IO.getStderr).putStrLn "usage: lean --run proof/ShapeCore.lean CHECK.json"; pure 2
