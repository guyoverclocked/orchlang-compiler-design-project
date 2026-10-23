import Std

/- A feasibility core, NOT a verification of the C++ analyzer or probabilistic
   relational soundness. One synthetic resource unit, bounded nondeterminism,
   all attempts charged, no text/store/lowering/adapter model. Primitive call
   bounds are constructor premises. No claim that those premises hold remotely. -/
namespace OrchLang

structure Event where
  contract : Nat
  input : Nat
  output : Nat
  failed : Bool
deriving DecidableEq, Repr

def usage : List Event → Nat
  | [] => 0
  | e :: es => e.input + e.output + usage es

theorem usage_append (a b : List Event) : usage (a ++ b) = usage a + usage b := by
  induction a with
  | nil => simp [usage]
  | cons e es ih => simp [usage, ih, Nat.add_assoc]

inductive Core where
  | skip
  | call (contract cap : Nat)
  | seq (a b : Core)
  | branch (a b : Core)
  | repeat (n : Nat) (body : Core)

def bound : Core → Nat
  | .skip => 0
  | .call _ cap => cap
  | .seq a b => bound a + bound b
  | .branch a b => max (bound a) (bound b)
  | .repeat n body => n * bound body

-- A failure is still an event with nonnegative billed usage. Repeat permits
-- early stopping after any prefix of at most n attempts, including zero.
inductive Executes : Core → List Event → Prop where
  | skip : Executes .skip []
  | call {k cap : Nat} {e : Event} (identity : e.contract = k)
      (primitiveBound : e.input + e.output ≤ cap) : Executes (.call k cap) [e]
  | seq {a b x y} : Executes a x → Executes b y → Executes (.seq a b) (x ++ y)
  | left {a b x} : Executes a x → Executes (.branch a b) x
  | right {a b x} : Executes b x → Executes (.branch a b) x
  | stop {n body} : Executes (.repeat n body) []
  | again {n body x y} : Executes body x → Executes (.repeat n body) y →
      Executes (.repeat (n + 1) body) (x ++ y)

theorem unary_sound {c : Core} {trace : List Event} (h : Executes c trace) :
    usage trace ≤ bound c := by
  induction h with
  | skip => simp [usage, bound]
  | call identity primitiveBound => simpa [usage, bound] using primitiveBound
  | seq hx hy ihx ihy => simp only [usage_append, bound]; omega
  | left hx ih => exact Nat.le_trans ih (Nat.le_max_left _ _)
  | right hx ih => exact Nat.le_trans ih (Nat.le_max_right _ _)
  | stop => simp [usage, bound]
  | again hx hy ihx ihy =>
      simp only [bound] at ihy
      simp only [usage_append, bound, Nat.add_mul, Nat.one_mul]
      omega

-- A stronger observer's equality is preserved under deterministic projection.
-- This elementary fact is not a novelty claim or a distributional theorem.
theorem observer_projection {α β : Type} (project : α → β) {x y : α}
    (same : x = y) : project x = project y := by
  exact congrArg project same

-- Identical branch trace semantics compose; unequal upper bounds alone are
-- deliberately not a premise of any relational rule in this core.
theorem identical_branches {a : Core} {trace : List Event} :
    Executes (.branch a a) trace ↔ Executes a trace := by
  constructor
  · intro h
    cases h with
    | left h => exact h
    | right h => exact h
  · intro h
    exact Executes.left h

#print axioms unary_sound
#print axioms observer_projection
#print axioms identical_branches

end OrchLang
