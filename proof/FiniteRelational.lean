import Std
import Std.Internal.Rat
import Lean

/- Closed-request feasibility fragment. Finite kernels are external parameters.
   No source parser, stores or response-dependent requests. Early-stop retry
   bills failed attempts and stops iff the attempt contains no failed event.
   We prove equality of the explicit weighted trace lists, which is stronger
   than equality after merging duplicate observations. If kernels are valid
   finite probability distributions, the result is distributional equality.
   Kernel validity and deployed adapter correspondence are NOT proved here. -/
namespace OrchLang.Finite

structure Action where
  contract : String
  request : String
deriving DecidableEq

structure Event where
  contract : String
  input : Nat
  output : Nat
  failed : Bool
deriving DecidableEq

abbrev Distribution := List (List Event × Std.Internal.Rat)
abbrev Kernel := Action → Distribution

def unit : Distribution := [([], 1)]

def compose (a b : Distribution) : Distribution :=
  a.flatMap fun x => b.map fun y => (x.1 ++ y.1, x.2 * y.2)

def repeatDistribution : Nat → Distribution → Distribution
  | 0, _ => unit
  | n + 1, d => compose d (repeatDistribution n d)

-- Every attempt is billed, including errors. Stop when no call failed.
def retryDistribution : Nat → Distribution → Distribution
  | 0, _ => unit
  | n + 1, d => d.flatMap fun x =>
      if x.1.any Event.failed then
        (retryDistribution n d).map fun y => (x.1 ++ y.1, x.2 * y.2)
      else [x]

inductive Plan where
  | skip
  | call (action : Action)
  | seq (a b : Plan)
  | repeat (n : Nat) (body : Plan)
  | retry (n : Nat) (body : Plan)
deriving DecidableEq

inductive Program where
  | skip
  | call (action : Action)
  | seq (a b : Program)
  | secretBranch (guard : Nat) (a b : Program)
  | repeat (n : Nat) (body : Program)
  | retry (n : Nat) (body : Program)

def denotePlan (kernel : Kernel) : Plan → Distribution
  | .skip => unit
  | .call action => kernel action
  | .seq a b => compose (denotePlan kernel a) (denotePlan kernel b)
  | .repeat n body => repeatDistribution n (denotePlan kernel body)
  | .retry n body => retryDistribution n (denotePlan kernel body)

def denote (kernel : Kernel) (secrets : Nat → Bool) : Program → Distribution
  | .skip => unit
  | .call action => kernel action
  | .seq a b => compose (denote kernel secrets a) (denote kernel secrets b)
  | .secretBranch g a b => if secrets g then denote kernel secrets a else denote kernel secrets b
  | .repeat n body => repeatDistribution n (denote kernel secrets body)
  | .retry n body => retryDistribution n (denote kernel secrets body)

def normalize : Program → Option Plan
  | .skip => some .skip
  | .call action => some (.call action)
  | .seq a b => do
      let a' ← normalize a
      let b' ← normalize b
      pure (.seq a' b')
  | .secretBranch _ a b => do
      let a' ← normalize a
      let b' ← normalize b
      if a' = b' then some a' else none
  | .repeat n body => do
      let body' ← normalize body
      pure (.repeat n body')
  | .retry n body => do
      let body' ← normalize body
      pure (.retry n body')

theorem normalize_correct (program : Program) (kernel : Kernel) (secrets : Nat → Bool) :
    ∀ plan, normalize program = some plan → denote kernel secrets program = denotePlan kernel plan := by
  induction program with
  | skip => intro plan h; cases h; rfl
  | call action => intro plan h; cases h; rfl
  | seq a b iha ihb =>
      intro plan h
      cases ha : normalize a with
      | none => simp [normalize, ha] at h
      | some pa =>
          cases hb : normalize b with
          | none => simp [normalize, ha, hb] at h
          | some pb =>
              simp [normalize, ha, hb] at h
              cases h
              simp [denote, denotePlan, iha pa ha, ihb pb hb]
  | secretBranch guard a b iha ihb =>
      intro plan h
      cases ha : normalize a with
      | none => simp [normalize, ha] at h
      | some pa =>
          cases hb : normalize b with
          | none => simp [normalize, ha, hb] at h
          | some pb =>
              by_cases same : pa = pb
              · subst pb
                simp [normalize, ha, hb] at h
                cases h
                simp [denote, iha plan ha, ihb plan hb]
              · simp [normalize, ha, hb, same] at h
  | «repeat» n body ih =>
      intro plan h
      cases hb : normalize body with
      | none => simp [normalize, hb] at h
      | some pb =>
          simp [normalize, hb] at h
          cases h
          simp [denote, denotePlan, ih pb hb]
  | retry n body ih =>
      intro plan h
      cases hb : normalize body with
      | none => simp [normalize, hb] at h
      | some pb =>
          simp [normalize, hb] at h
          cases h
          simp [denote, denotePlan, ih pb hb]

theorem relational_sound (program : Program) (kernel : Kernel) (plan : Plan)
    (accepted : normalize program = some plan) (left right : Nat → Bool) :
    denote kernel left program = denote kernel right program := by
  exact (normalize_correct program kernel left plan accepted).trans
    (normalize_correct program kernel right plan accepted).symm

theorem observer_projection (program : Program) (kernel : Kernel) (plan : Plan)
    (accepted : normalize program = some plan) (left right : Nat → Bool)
    {α : Type} (observer : List Event → α) :
    (denote kernel left program).map (fun x => (observer x.1, x.2)) =
    (denote kernel right program).map (fun x => (observer x.1, x.2)) := by
  rw [relational_sound program kernel plan accepted left right]

def checkCertificate (program : Program) (plan : Plan) : Bool :=
  decide (normalize program = some plan)

theorem certificate_sound (program : Program) (kernel : Kernel) (plan : Plan)
    (checked : checkCertificate program plan = true) (left right : Nat → Bool) :
    denote kernel left program = denote kernel right program := by
  apply relational_sound program kernel plan
  simpa [checkCertificate] using checked

private def exampleAction : Action := ⟨"finite-contract-v1", "yes"⟩
private def otherAction : Action := ⟨"finite-contract-v1", "no!"⟩
#guard checkCertificate (.secretBranch 0 (.call exampleAction) (.call exampleAction))
  (.call exampleAction)
#guard !(checkCertificate (.secretBranch 0 (.call exampleAction) (.call otherAction))
  (.call exampleAction))
#guard !(checkCertificate (.call exampleAction) (.call otherAction))
#guard checkCertificate (.retry 2 (.secretBranch 0 (.call exampleAction) (.call exampleAction)))
  (.retry 2 (.call exampleAction))
#guard !(checkCertificate (.retry 2 (.call exampleAction)) (.retry 1 (.call exampleAction)))
private def okEvent : Event := ⟨"c", 3, 1, false⟩
private def errorEvent : Event := ⟨"c", 3, 0, true⟩
#guard retryDistribution 2 [([okEvent], 1/2), ([errorEvent], 1/2)] =
  [([okEvent], 1/2), ([errorEvent, okEvent], 1/4), ([errorEvent, errorEvent], 1/4)]

#print axioms normalize_correct
#print axioms relational_sound
#print axioms observer_projection
#print axioms certificate_sound

end OrchLang.Finite

/- The executable consumes JSON data, never generated Lean code. Decoding is
   fuel-bounded and rejects unknown tags/arity. Its soundness is relative to the
   decoded core; source parsing and JSON-library correctness remain trusted. -/
namespace OrchLang.Finite
open Lean

private def fields (j : Json) (arity : Nat) : Except String (Array Json) := do
  let a ← j.getArr?
  if a.size != arity then throw "wrong constructor arity"
  pure a

def decodeProgram : Nat → Json → Except String Program
  | 0, _ => .error "core nesting limit"
  | fuel + 1, j => do
      let a ← j.getArr?
      let tag ← (← j.getArrVal? 0).getStr?
      match tag with
      | "skip" => let _ ← fields j 1; pure .skip
      | "call" =>
          let _ ← fields j 3
          pure (.call ⟨← a[1]!.getStr?, ← a[2]!.getStr?⟩)
      | "seq" =>
          let _ ← fields j 3
          pure (.seq (← decodeProgram fuel a[1]!) (← decodeProgram fuel a[2]!))
      | "branch" =>
          let _ ← fields j 4
          pure (.secretBranch (← a[1]!.getNat?)
            (← decodeProgram fuel a[2]!) (← decodeProgram fuel a[3]!))
      | "repeat" =>
          let _ ← fields j 3
          let n ← a[1]!.getNat?
          if n > 16 then throw "repeat limit"
          pure (.repeat n (← decodeProgram fuel a[2]!))
      | "retry" =>
          let _ ← fields j 3
          let n ← a[1]!.getNat?
          if n > 16 then throw "retry limit"
          pure (.retry n (← decodeProgram fuel a[2]!))
      | _ => throw "unknown core constructor"

def decodePlan : Nat → Json → Except String Plan
  | 0, _ => .error "plan nesting limit"
  | fuel + 1, j => do
      let a ← j.getArr?
      let tag ← (← j.getArrVal? 0).getStr?
      match tag with
      | "skip" => let _ ← fields j 1; pure .skip
      | "call" =>
          let _ ← fields j 3
          pure (.call ⟨← a[1]!.getStr?, ← a[2]!.getStr?⟩)
      | "seq" =>
          let _ ← fields j 3
          pure (.seq (← decodePlan fuel a[1]!) (← decodePlan fuel a[2]!))
      | "repeat" =>
          let _ ← fields j 3
          let n ← a[1]!.getNat?
          if n > 16 then throw "repeat limit"
          pure (.repeat n (← decodePlan fuel a[2]!))
      | "retry" =>
          let _ ← fields j 3
          let n ← a[1]!.getNat?
          if n > 16 then throw "retry limit"
          pure (.retry n (← decodePlan fuel a[2]!))
      | _ => throw "unknown plan constructor"

def checkDecoded (programJson planJson : Json) : Except String Bool :=
  match decodeProgram 256 programJson, decodePlan 256 planJson with
  | .ok program, .ok plan => .ok (checkCertificate program plan)
  | .error e, _ => .error e
  | _, .error e => .error e

theorem decoded_certificate_sound (pj cj : Json) (program : Program) (plan : Plan)
    (hp : decodeProgram 256 pj = .ok program) (hc : decodePlan 256 cj = .ok plan)
    (checked : checkDecoded pj cj = .ok true) (kernel : Kernel) (left right : Nat → Bool) :
    denote kernel left program = denote kernel right program := by
  apply certificate_sound program kernel plan
  simpa [checkDecoded, hp, hc, Except.bind, Except.map] using checked

#print axioms decoded_certificate_sound

def checkBatch (j : Json) : Except String Json := do
  let cases ← j.getArr?
  let results ← cases.mapM fun item => do
    let pair ← fields item 2
    pure (Json.bool (← checkDecoded pair[0]! pair[1]!))
  pure (Json.arr results)
end OrchLang.Finite

def main (args : List String) : IO UInt32 := do
  match args with
  | [path] =>
      let contents ← IO.FS.readFile path
      match Lean.Json.parse contents >>= OrchLang.Finite.checkBatch with
      | .ok result => IO.println result.compress; pure 0
      | .error error => (← IO.getStderr).putStrLn error; pure 2
  | _ => (← IO.getStderr).putStrLn "usage: lean --run proof/FiniteRelational.lean BATCH.json"; pure 2
