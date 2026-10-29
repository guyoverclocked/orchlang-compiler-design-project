import Std
import Lean

/- A separate aggregate-only judgment for exactly two independent closed calls.
   Each finite kernel has natural weights and a common positive denominator;
   arbitrary rational finite tables can be represented this way. The algebraic
   theorem works even for unnormalized tables. Probability interpretation needs
   each row's weights to sum to its denominator. No stores, dependent requests,
   timing, output contents, retries or mutable provider state are modeled. -/
namespace OrchLang.Aggregate

structure Action where
  contract : String
  request : String
deriving DecidableEq

structure Outcome where
  response : String
  failed : Bool
  weight : Nat

structure Usage where
  input : Nat
  output : Nat
  calls : Nat
  failures : Nat
deriving DecidableEq

abbrev Observation := String → Usage
abbrev Kernel := Action → List Outcome

def addUsage (a b : Usage) : Usage :=
  ⟨a.input+b.input, a.output+b.output, a.calls+b.calls, a.failures+b.failures⟩

def observe (a : Action) (o : Outcome) : Observation := fun contract =>
  if contract = a.contract then
    ⟨a.request.utf8ByteSize, o.response.utf8ByteSize, 1, if o.failed then 1 else 0⟩
  else ⟨0,0,0,0⟩

def pairObservation (a b : Action) (x y : Outcome) : Observation := fun contract =>
  addUsage (observe a x contract) (observe b y contract)

theorem pairObservation_comm (a b : Action) (x y : Outcome) :
    pairObservation a b x y = pairObservation b a y x := by
  funext contract
  simp [pairObservation, addUsage, Nat.add_comm]

def samples (kernel : Kernel) (a b : Action) : List (Observation × Nat) :=
  (kernel a).flatMap fun x => (kernel b).map fun y =>
    (pairObservation a b x y, x.weight*y.weight)

-- Transposing a finite Cartesian enumeration only permutes its result list.
theorem flatMap_map_transpose {α β γ : Type} (a : List α) (b : List β) (f : α → β → γ) :
    List.Perm (a.flatMap fun x => b.map (f x))
      (b.flatMap fun y => a.map (fun x => f x y)) := by
  induction a with
  | nil => simp
  | cons x xs ih =>
      simp only [List.flatMap_cons, List.map_cons]
      apply List.Perm.trans (List.Perm.append (List.Perm.refl _) ih)
      clear ih
      induction b with
      | nil => simp
      | cons y ys ih =>
          simp only [List.map_cons, List.flatMap_cons, List.cons_append]
          apply List.Perm.cons
          exact (List.perm_append_comm_assoc (ys.map (f x))
            (xs.map (fun x => f x y))
            (ys.flatMap fun y => xs.map (fun x => f x y))).trans (ih.append_left _)

theorem samples_comm (kernel : Kernel) (a b : Action) :
    List.Perm (samples kernel a b) (samples kernel b a) := by
  unfold samples
  have h := flatMap_map_transpose (kernel a) (kernel b)
    (fun x y => (pairObservation a b x y, x.weight*y.weight))
  simpa only [pairObservation_comm a b, Nat.mul_comm] using h

-- A histogram is the exact integer numerator assigned to any Boolean event of
-- the aggregate observation. This proves equality of masses, not list order.
def mass (test : Observation → Bool) : List (Observation × Nat) → Nat
  | [] => 0
  | (o,w) :: rest => (if test o then w else 0) + mass test rest

theorem mass_perm (test : Observation → Bool) {a b : List (Observation × Nat)}
    (h : List.Perm a b) : mass test a = mass test b := by
  induction h with
  | nil => rfl
  | cons x h ih => simp [mass, ih]
  | swap x y rest => simp [mass, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

theorem independent_calls_aggregate (kernel : Kernel) (denominator : Action → Nat)
    (a b : Action) (test : Observation → Bool) :
    (mass test (samples kernel a b), denominator a * denominator b) =
      (mass test (samples kernel b a), denominator b * denominator a) := by
  rw [mass_perm test (samples_comm kernel a b), Nat.mul_comm (denominator a)]

structure Program where
  leftFirst : Action
  leftSecond : Action
  rightFirst : Action
  rightSecond : Action

def checkProgram (p : Program) : Bool :=
  decide ((p.leftFirst = p.rightFirst ∧ p.leftSecond = p.rightSecond) ∨
    (p.leftFirst = p.rightSecond ∧ p.leftSecond = p.rightFirst))

theorem decision_sound (p : Program) (checked : checkProgram p = true)
    (kernel : Kernel) (denominator : Action → Nat) (test : Observation → Bool) :
    (mass test (samples kernel p.leftFirst p.leftSecond),
      denominator p.leftFirst * denominator p.leftSecond) =
    (mass test (samples kernel p.rightFirst p.rightSecond),
      denominator p.rightFirst * denominator p.rightSecond) := by
  have h : (p.leftFirst = p.rightFirst ∧ p.leftSecond = p.rightSecond) ∨
      (p.leftFirst = p.rightSecond ∧ p.leftSecond = p.rightFirst) := by
    simpa [checkProgram] using checked
  rcases h with ⟨h1,h2⟩ | ⟨h1,h2⟩
  · rw [h1,h2]
  · rw [h1,h2]
    exact independent_calls_aggregate kernel denominator p.rightSecond p.rightFirst test

-- A trusted caller may retain the actual outcomes without observing schedule.
-- Results are a multiset indexed by full Action, response contents and status;
-- two draws of the same action are retained with multiplicity, not overwritten.
abbrev PrivateResults := Action → String → Bool → Nat

def oneResult (a : Action) (x : Outcome) : PrivateResults := fun action response failed =>
  if a = action ∧ x.response = response ∧ x.failed = failed then 1 else 0

def pairResults (a b : Action) (x y : Outcome) : PrivateResults := fun action response failed =>
  oneResult a x action response failed + oneResult b y action response failed

theorem pairResults_comm (a b : Action) (x y : Outcome) :
    pairResults a b x y = pairResults b a y x := by
  funext action response failed
  simp [pairResults, Nat.add_comm]

structure JointObservation where
  usage : Observation
  results : PrivateResults

def pairJoint (a b : Action) (x y : Outcome) : JointObservation :=
  ⟨pairObservation a b x y, pairResults a b x y⟩

theorem pairJoint_comm (a b : Action) (x y : Outcome) :
    pairJoint a b x y = pairJoint b a y x := by
  unfold pairJoint
  rw [pairObservation_comm, pairResults_comm]

def jointSamples (kernel : Kernel) (a b : Action) : List (JointObservation × Nat) :=
  (kernel a).flatMap fun x => (kernel b).map fun y =>
    (pairJoint a b x y, x.weight*y.weight)

theorem jointSamples_comm (kernel : Kernel) (a b : Action) :
    List.Perm (jointSamples kernel a b) (jointSamples kernel b a) := by
  unfold jointSamples
  have h := flatMap_map_transpose (kernel a) (kernel b)
    (fun x y => (pairJoint a b x y, x.weight*y.weight))
  simpa only [pairJoint_comm a b, Nat.mul_comm] using h

def jointMass (test : JointObservation → Bool) : List (JointObservation × Nat) → Nat
  | [] => 0
  | (o,w) :: rest => (if test o then w else 0) + jointMass test rest

theorem jointMass_perm (test : JointObservation → Bool) {a b : List (JointObservation × Nat)}
    (h : List.Perm a b) : jointMass test a = jointMass test b := by
  induction h with
  | nil => rfl
  | cons x h ih => simp [jointMass, ih]
  | swap x y rest => simp [jointMass, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

theorem independent_calls_private_results (kernel : Kernel) (denominator : Action → Nat)
    (a b : Action) (test : JointObservation → Bool) :
    (jointMass test (jointSamples kernel a b), denominator a * denominator b) =
      (jointMass test (jointSamples kernel b a), denominator b * denominator a) := by
  rw [jointMass_perm test (jointSamples_comm kernel a b), Nat.mul_comm (denominator a)]

theorem private_results_decision_sound (p : Program) (checked : checkProgram p = true)
    (kernel : Kernel) (denominator : Action → Nat) (test : JointObservation → Bool) :
    (jointMass test (jointSamples kernel p.leftFirst p.leftSecond),
      denominator p.leftFirst * denominator p.leftSecond) =
    (jointMass test (jointSamples kernel p.rightFirst p.rightSecond),
      denominator p.rightFirst * denominator p.rightSecond) := by
  have h : (p.leftFirst = p.rightFirst ∧ p.leftSecond = p.rightSecond) ∨
      (p.leftFirst = p.rightSecond ∧ p.leftSecond = p.rightFirst) := by
    simpa [checkProgram] using checked
  rcases h with ⟨h1,h2⟩ | ⟨h1,h2⟩
  · rw [h1,h2]
  · rw [h1,h2]
    exact independent_calls_private_results kernel denominator p.rightSecond p.rightFirst test

#print axioms pairObservation_comm
#print axioms samples_comm
#print axioms mass_perm
#print axioms independent_calls_aggregate
#print axioms decision_sound
#print axioms independent_calls_private_results
#print axioms private_results_decision_sound
end OrchLang.Aggregate

namespace OrchLang.Aggregate
open Lean

private def fields (j : Json) (arity : Nat) : Except String (Array Json) := do
  let a ← j.getArr?
  if a.size != arity then throw "wrong constructor arity"
  pure a

private def decodeAction (j : Json) : Except String Action := do
  let a ← fields j 3
  if (← a[0]!.getStr?) != "call" then throw "expected closed call"
  pure ⟨← a[1]!.getStr?, ← a[2]!.getStr?⟩

private def decodePair (j : Json) : Except String (Action × Action) := do
  let a ← fields j 3
  if (← a[0]!.getStr?) != "seq" then throw "expected exactly two closed calls"
  pure (← decodeAction a[1]!, ← decodeAction a[2]!)

def decodeProgram (j : Json) : Except String Program := do
  let a ← fields j 4
  if (← a[0]!.getStr?) != "branch" then throw "expected one secret branch"
  let _ ← a[1]!.getNat?
  let left ← decodePair a[2]!
  let right ← decodePair a[3]!
  pure ⟨left.1,left.2,right.1,right.2⟩

def decideDecoded (j : Json) : Except String Bool :=
  match decodeProgram j with
  | .ok p => .ok (checkProgram p)
  | .error e => .error e

theorem decoded_decision_sound (j : Json) (p : Program)
    (decoded : decodeProgram j = .ok p) (checked : decideDecoded j = .ok true)
    (kernel : Kernel) (denominator : Action → Nat) (test : Observation → Bool) :
    (mass test (samples kernel p.leftFirst p.leftSecond),
      denominator p.leftFirst * denominator p.leftSecond) =
    (mass test (samples kernel p.rightFirst p.rightSecond),
      denominator p.rightFirst * denominator p.rightSecond) := by
  apply decision_sound p
  simpa [decideDecoded, decoded] using checked

theorem decoded_private_results_sound (j : Json) (p : Program)
    (decoded : decodeProgram j = .ok p) (checked : decideDecoded j = .ok true)
    (kernel : Kernel) (denominator : Action → Nat) (test : JointObservation → Bool) :
    (jointMass test (jointSamples kernel p.leftFirst p.leftSecond),
      denominator p.leftFirst * denominator p.leftSecond) =
    (jointMass test (jointSamples kernel p.rightFirst p.rightSecond),
      denominator p.rightFirst * denominator p.rightSecond) := by
  apply private_results_decision_sound p
  simpa [decideDecoded, decoded] using checked

#print axioms decoded_decision_sound
#print axioms decoded_private_results_sound

private structure Row where
  action : Action
  denominator : Nat
  outcomes : List Outcome

private def decodeRows (j : Json) : Except String (List Row) := do
  let rows ← (← j.getArr?).toList.mapM fun j => do
    let a ← fields j 4
    let denominator ← a[2]!.getNat?
    if denominator = 0 then throw "zero kernel denominator"
    let outcomes ← (← a[3]!.getArr?).toList.mapM fun item => do
      let o ← fields item 3
      pure (Outcome.mk (← o[0]!.getStr?) (← o[1]!.getBool?) (← o[2]!.getNat?))
    if outcomes.length > 32 then throw "kernel arity limit"
    if outcomes.foldl (fun total o => total+o.weight) 0 != denominator then
      throw "kernel row numerator mass differs from denominator"
    pure (Row.mk (Action.mk (← a[0]!.getStr?) (← a[1]!.getStr?)) denominator outcomes)
  let keys := rows.map Row.action
  if keys.eraseDups.length != keys.length then throw "duplicate kernel action"
  if rows.length > 64 then throw "kernel table limit"
  pure rows

private def lookup (rows : List Row) (a : Action) : Except String Row :=
  match rows.find? (fun row => decide (row.action = a)) with
  | some row => .ok row
  | none => .error "missing full-action kernel"

private def jsonUsage (o : Observation) (contracts : List String) : Json :=
  toJson (contracts.map fun c =>
    let u := o c
    toJson ([toJson c,toJson u.input,toJson u.output,toJson u.calls,toJson u.failures] : List Json))

private def jsonEvent (a : Action) (o : Outcome) : Json :=
  toJson ([toJson a.contract,toJson a.request.utf8ByteSize,toJson o.response.utf8ByteSize,
    toJson o.failed] : List Json)

private def executePair (rows : List Row) (contracts : List String)
    (a b : Action) : Except String Json := do
  let left ← lookup rows a
  let right ← lookup rows b
  pure (toJson (left.outcomes.flatMap fun x => right.outcomes.map fun y =>
    Json.mkObj [("aggregate",jsonUsage (pairObservation a b x y) contracts),
      ("ordered",toJson ([jsonEvent a x,jsonEvent b y] : List Json)),
      ("p",toJson ([x.weight*y.weight,left.denominator*right.denominator] : List Nat))]))

private def jsonResult (a : Action) (o : Outcome) : Json :=
  toJson ([toJson a.contract,toJson a.request,toJson o.response,toJson o.failed] : List Json)

private def executePrivatePair (rows : List Row) (contracts : List String)
    (a b : Action) : Except String Json := do
  let left ← lookup rows a
  let right ← lookup rows b
  pure (toJson (left.outcomes.flatMap fun x => right.outcomes.map fun y =>
    Json.mkObj [("aggregate",jsonUsage (pairObservation a b x y) contracts),
      ("private_results",toJson ([jsonResult a x,jsonResult b y] : List Json)),
      ("p",toJson ([x.weight*y.weight,left.denominator*right.denominator] : List Nat))]))

def checkBatch (j : Json) : Except String Json := do
  let cases ← j.getArr?
  let result ← cases.mapM fun row => do
    let pj ← row.getObjVal? "program"
    let p ← decodeProgram pj
    let checked ← decideDecoded pj
    let execute ← (← row.getObjVal? "execute").getBool?
    if !execute then pure (Json.mkObj [("checked",toJson checked)]) else
      let rows ← decodeRows (← row.getObjVal? "kernels")
      let contracts := [p.leftFirst.contract,p.leftSecond.contract,
        p.rightFirst.contract,p.rightSecond.contract] |>.eraseDups
      let left ← executePair rows contracts p.leftFirst p.leftSecond
      let right ← executePair rows contracts p.rightFirst p.rightSecond
      pure (Json.mkObj [("checked",toJson checked),("left",left),("right",right)])
  pure (Json.arr result)

def privateBatch (j : Json) : Except String Json := do
  let cases ← j.getArr?
  let result ← cases.mapM fun row => do
    let pj ← row.getObjVal? "program"
    let p ← decodeProgram pj
    let checked ← decideDecoded pj
    let rows ← decodeRows (← row.getObjVal? "kernels")
    let contracts := [p.leftFirst.contract,p.leftSecond.contract,
      p.rightFirst.contract,p.rightSecond.contract] |>.eraseDups
    let left ← executePrivatePair rows contracts p.leftFirst p.leftSecond
    let right ← executePrivatePair rows contracts p.rightFirst p.rightSecond
    pure (Json.mkObj [("checked",toJson checked),("left",left),("right",right)])
  pure (Json.arr result)

end OrchLang.Aggregate

def main (args : List String) : IO UInt32 := do
  match args with
  | [path] | ["private",path] =>
      let contents ← IO.FS.readFile path
      if contents.utf8ByteSize > 16000000 then
        (← IO.getStderr).putStrLn "batch byte limit"; return 2
      let checker := if args.length = 2 then OrchLang.Aggregate.privateBatch else OrchLang.Aggregate.checkBatch
      match Lean.Json.parse contents >>= checker with
      | .ok result => IO.println result.compress; return 0
      | .error error => (← IO.getStderr).putStrLn error; return 2
  | _ => (← IO.getStderr).putStrLn "usage: lean --run proof/AggregateReordering.lean BATCH.json"; return 2
