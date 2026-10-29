import Std
import Std.Internal.Rat
import Lean

/- Text-valued, stateless dataflow core. Secret Booleans affect only control;
   public text/Boolean inputs are identical in the compared executions.
   Response text is stored and may construct downstream requests. No source
   parser or provider implementation is verified by this file. -/
namespace OrchLang.Dataflow
abbrev Rat := Std.Internal.Rat
abbrev Store := Nat → String

inductive Text where
  | literal (value : String)
  | var (slot : Nat)
  | append (a b : Text)
deriving DecidableEq

def text (env : Store) : Text → String
  | .literal value => value
  | .var slot => env slot
  | .append a b => text env a ++ text env b

-- Canonicalize the free string monoid without assuming anything about variables.
-- Calls still require equal full serialized requests, contracts and response slots.
def appendText : Text → Text → Text
  | .append a b, c => appendText a (appendText b c)
  | .literal s, c =>
      if s = "" then c else
      match c with
      | .literal t => .literal (s ++ t)
      | .append (.literal t) d => .append (.literal (s ++ t)) d
      | _ => .append (.literal s) c
  | .var i, c => if c = .literal "" then .var i else .append (.var i) c

theorem appendText_correct (env : Store) (a b : Text) :
    text env (appendText a b) = text env a ++ text env b := by
  induction a generalizing b with
  | append a c iha ihc => simp [appendText, text, iha, ihc, String.append_assoc]
  | var i => by_cases h : b = .literal "" <;> simp [appendText, h, text]
  | literal s =>
      by_cases h : s = ""
      · simp [appendText, h, text]
      · cases b with
        | literal t => simp [appendText, h, text]
        | var i => simp [appendText, h, text]
        | append b c => cases b <;> simp [appendText, h, text, String.append_assoc]

def normalizeText : Text → Text
  | .literal s => .literal s
  | .var i => .var i
  | .append a b => appendText (normalizeText a) (normalizeText b)

theorem normalizeText_correct (env : Store) (request : Text) :
    text env (normalizeText request) = text env request := by
  induction request with
  | literal s => rfl
  | var i => rfl
  | append a b iha ihb => simp [normalizeText, appendText_correct, text, iha, ihb]

structure Event where
  contract : String
  input : Nat
  output : Nat
  failed : Bool
deriving DecidableEq

structure Outcome where
  response : String
  failed : Bool
  weight : Rat

abbrev Kernel := String → String → List Outcome

structure Execution where
  store : Store
  trace : List Event
  requests : List String
  weight : Rat

abbrev Semantics := Store → List Execution

def unit : Semantics := fun env => [⟨env, [], [], 1⟩]

def call (kernel : Kernel) (slot : Nat) (contract : String) (request : Text) : Semantics :=
  fun env =>
    let serialized := text env request
    (kernel contract serialized).map fun o =>
      ⟨(fun i => if i = slot then o.response else env i),
        [⟨contract, serialized.utf8ByteSize, o.response.utf8ByteSize, o.failed⟩],
        [serialized], o.weight⟩

def join (x y : Execution) : Execution :=
  ⟨y.store, x.trace ++ y.trace, x.requests ++ y.requests, x.weight * y.weight⟩

def compose (a b : Semantics) : Semantics := fun env =>
  (a env).flatMap fun x => (b x.store).map (join x)

theorem rat_one_mul (a : Rat) : (1 : Rat) * a = a := by
  have hn : (1 : Rat).num = 1 := rfl
  have hd : (1 : Rat).den = 1 := rfl
  change Std.Internal.Rat.mul 1 a = a
  cases a
  simp [Std.Internal.Rat.mul, hn, hd]

theorem rat_mul_one (a : Rat) : a * (1 : Rat) = a := by
  have hn : (1 : Rat).num = 1 := rfl
  have hd : (1 : Rat).den = 1 := rfl
  change Std.Internal.Rat.mul a 1 = a
  cases a
  simp [Std.Internal.Rat.mul, hn, hd]

theorem compose_unit_left (a : Semantics) : compose unit a = a := by
  funext env
  simp only [compose, unit, List.flatMap_singleton]
  apply List.map_id''
  intro x
  cases x
  simp [join, rat_one_mul]

theorem compose_unit_right (a : Semantics) : compose a unit = a := by
  funext env
  simp [compose, unit, join, rat_mul_one]

#print axioms rat_one_mul
#print axioms rat_mul_one
#print axioms compose_unit_left
#print axioms compose_unit_right

-- Retry bodies are lexical: their local bindings do not escape an attempt.
-- All events, including billed failures, survive. Stop iff no call failed.
def retry : Nat → Semantics → Semantics
  | 0, _ => unit
  | n + 1, body => fun env =>
      (body env).flatMap fun x =>
        if x.trace.any Event.failed then
          (retry n body env).map (join x)
        else [{x with store := env}]

inductive Plan where
  | skip
  | call (slot : Nat) (contract : String) (request : Text)
  | seq (a b : Plan)
  | publicBranch (guard : Nat) (a b : Plan)
  | retry (n : Nat) (body : Plan)
deriving DecidableEq

inductive Program where
  | skip
  | call (slot : Nat) (contract : String) (request : Text)
  | seq (a b : Program)
  | publicBranch (guard : Nat) (a b : Program)
  | secretBranch (guard : Nat) (a b : Program)
  | retry (n : Nat) (body : Program)

def denotePlan (kernel : Kernel) (public : Nat → Bool) : Plan → Semantics
  | .skip => unit
  | .call slot contract request => call kernel slot contract request
  | .seq a b => compose (denotePlan kernel public a) (denotePlan kernel public b)
  | .publicBranch g a b => if public g then denotePlan kernel public a else denotePlan kernel public b
  | .retry n body => retry n (denotePlan kernel public body)

def denote (kernel : Kernel) (public secret : Nat → Bool) : Program → Semantics
  | .skip => unit
  | .call slot contract request => call kernel slot contract request
  | .seq a b => compose (denote kernel public secret a) (denote kernel public secret b)
  | .publicBranch g a b => if public g then denote kernel public secret a else denote kernel public secret b
  | .secretBranch g a b => if secret g then denote kernel public secret a else denote kernel public secret b
  | .retry n body => retry n (denote kernel public secret body)

def sequencePlan (a b : Plan) : Plan :=
  match a, b with
  | .skip, _ => b
  | _, .skip => a
  | _, _ => .seq a b

theorem sequencePlan_correct (kernel : Kernel) (public : Nat → Bool) (a b : Plan) :
    denotePlan kernel public (sequencePlan a b) =
      compose (denotePlan kernel public a) (denotePlan kernel public b) := by
  cases a <;> cases b <;>
    simp [sequencePlan, denotePlan, compose_unit_left, compose_unit_right]

def publicPlan (guard : Nat) (a b : Plan) : Plan :=
  if a = b then a else .publicBranch guard a b

theorem publicPlan_correct (kernel : Kernel) (public : Nat → Bool)
    (guard : Nat) (a b : Plan) :
    denotePlan kernel public (publicPlan guard a b) =
      (if public guard then denotePlan kernel public a else denotePlan kernel public b) := by
  by_cases h : a = b
  · simp [publicPlan, h]
  · simp [publicPlan, h, denotePlan]

theorem call_normalizeText (kernel : Kernel) (slot : Nat) (contract : String) (request : Text) :
    call kernel slot contract (normalizeText request) = call kernel slot contract request := by
  funext env
  simp [call, normalizeText_correct]

def normalize : Program → Option Plan
  | .skip => some .skip
  | .call slot contract request => some (.call slot contract (normalizeText request))
  | .seq a b => do
      let a' ← normalize a
      let b' ← normalize b
      pure (sequencePlan a' b')
  | .publicBranch g a b => do
      let a' ← normalize a
      let b' ← normalize b
      pure (publicPlan g a' b')
  | .secretBranch _ a b => do
      let a' ← normalize a
      let b' ← normalize b
      if a' = b' then some a' else none
  | .retry n body => do
      let body' ← normalize body
      pure (.retry n body')

theorem normalize_correct (program : Program) (kernel : Kernel) (public secret : Nat → Bool) :
    ∀ plan, normalize program = some plan →
      denote kernel public secret program = denotePlan kernel public plan := by
  induction program with
  | skip => intro plan h; cases h; rfl
  | call slot contract request =>
      intro plan h
      cases h
      exact (call_normalizeText kernel slot contract request).symm
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
              simp [denote, sequencePlan_correct, iha pa ha, ihb pb hb]
  | publicBranch g a b iha ihb =>
      intro plan h
      cases ha : normalize a with
      | none => simp [normalize, ha] at h
      | some pa =>
          cases hb : normalize b with
          | none => simp [normalize, ha, hb] at h
          | some pb =>
              simp [normalize, ha, hb] at h
              cases h
              simp [denote, publicPlan_correct, iha pa ha, ihb pb hb]
  | secretBranch g a b iha ihb =>
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
  | retry n body ih =>
      intro plan h
      cases hb : normalize body with
      | none => simp [normalize, hb] at h
      | some pb =>
          simp [normalize, hb] at h
          cases h
          simp [denote, denotePlan, ih pb hb]

def checkCertificate (program : Program) (plan : Plan) : Bool :=
  decide (normalize program = some plan)

-- Primary interface: a verified (incomplete) decision procedure. A saved plan is
-- only a diagnostic result: checking it recomputes normalize, not a cheaper proof.
def checkProgram (program : Program) : Bool := (normalize program).isSome

theorem relational_sound (program : Program) (plan : Plan)
    (checked : checkCertificate program plan = true) (kernel : Kernel)
    (public left right : Nat → Bool) :
    denote kernel public left program = denote kernel public right program := by
  have accepted : normalize program = some plan := by simpa [checkCertificate] using checked
  exact (normalize_correct program kernel public left plan accepted).trans
    (normalize_correct program kernel public right plan accepted).symm

theorem checkProgram_sound (program : Program) (checked : checkProgram program = true)
    (kernel : Kernel) (public left right : Nat → Bool) :
    denote kernel public left program = denote kernel public right program := by
  cases h : normalize program with
  | none => simp [checkProgram, h] at checked
  | some plan =>
      exact (normalize_correct program kernel public left plan h).trans
        (normalize_correct program kernel public right plan h).symm

theorem observer_projection (program : Program) (plan : Plan)
    (checked : checkCertificate program plan = true) (kernel : Kernel)
    (public left right : Nat → Bool) (env : Store) {α : Type}
    (observer : Execution → α) :
    (denote kernel public left program env).map observer =
    (denote kernel public right program env).map observer := by
  rw [relational_sound program plan checked kernel public left right]

-- Downstream requests retain response text, not only its length.
private def pipeline : Program :=
  .seq (.call 0 "c" (.literal "yes")) (.call 1 "c" (.append (.literal "next:") (.var 0)))
private def pipelinePlan : Plan :=
  .seq (.call 0 "c" (.literal "yes")) (.call 1 "c" (.append (.literal "next:") (.var 0)))
#guard checkCertificate (.secretBranch 0 pipeline pipeline) pipelinePlan
#guard !(checkCertificate (.secretBranch 0 pipeline
  (.seq (.call 0 "c" (.literal "yes")) (.call 1 "c" (.literal "next:x")))) pipelinePlan)
#guard text (fun _ => "é") (.append (.literal "next:") (.var 0)) = "next:é"

-- Strict gains over comparing raw request/plan trees, under the same kernels.
private def expandedRequest : Text :=
  .append (.append (.literal "Ne") (.literal "xt:")) (.append (.var 0) (.literal ""))
#guard expandedRequest != .append (.literal "Next:") (.var 0)
#guard normalizeText expandedRequest = .append (.literal "Next:") (.var 0)
#guard checkCertificate (.secretBranch 0
    (.call 1 "c" expandedRequest)
    (.call 1 "c" (.append (.literal "Next:") (.var 0))))
  (.call 1 "c" (.append (.literal "Next:") (.var 0)))
#guard checkCertificate (.secretBranch 0
    (.seq .skip (.publicBranch 0 pipeline pipeline)) pipeline) pipelinePlan

#print axioms appendText_correct
#print axioms normalizeText_correct
#print axioms sequencePlan_correct
#print axioms publicPlan_correct

#print axioms normalize_correct
#print axioms relational_sound
#print axioms checkProgram_sound
#print axioms observer_projection
end OrchLang.Dataflow

namespace OrchLang.Dataflow
open Lean

private def fields (j : Json) (arity : Nat) : Except String (Array Json) := do
  let a ← j.getArr?
  if a.size != arity then throw "wrong constructor arity"
  pure a

def decodeText : Nat → Json → Except String Text
  | 0, _ => .error "text nesting limit"
  | n+1, j => do
      let a ← j.getArr?
      match ← (← j.getArrVal? 0).getStr? with
      | "literal" => let _ ← fields j 2; pure (.literal (← a[1]!.getStr?))
      | "var" => let _ ← fields j 2; pure (.var (← a[1]!.getNat?))
      | "append" =>
          let _ ← fields j 3
          pure (.append (← decodeText n a[1]!) (← decodeText n a[2]!))
      | _ => throw "unknown text constructor"

def decodeProgram : Nat → Json → Except String Program
  | 0, _ => .error "program nesting limit"
  | n+1, j => do
      let a ← j.getArr?
      match ← (← j.getArrVal? 0).getStr? with
      | "skip" => let _ ← fields j 1; pure .skip
      | "call" =>
          let _ ← fields j 4
          pure (.call (← a[1]!.getNat?) (← a[2]!.getStr?) (← decodeText 128 a[3]!))
      | "seq" =>
          let _ ← fields j 3
          pure (.seq (← decodeProgram n a[1]!) (← decodeProgram n a[2]!))
      | "public" =>
          let _ ← fields j 4
          pure (.publicBranch (← a[1]!.getNat?) (← decodeProgram n a[2]!) (← decodeProgram n a[3]!))
      | "secret" =>
          let _ ← fields j 4
          pure (.secretBranch (← a[1]!.getNat?) (← decodeProgram n a[2]!) (← decodeProgram n a[3]!))
      | "retry" =>
          let _ ← fields j 3
          let count ← a[1]!.getNat?
          if count > 16 then throw "retry limit"
          pure (.retry count (← decodeProgram n a[2]!))
      | _ => throw "unknown program constructor"

def asPlan : Program → Except String Plan
  | .skip => .ok .skip
  | .call slot contract request => .ok (.call slot contract request)
  | .seq a b => return .seq (← asPlan a) (← asPlan b)
  | .publicBranch g a b => return .publicBranch g (← asPlan a) (← asPlan b)
  | .secretBranch _ _ _ => .error "plans cannot contain secrets"
  | .retry n body => return .retry n (← asPlan body)

def decodePlan (j : Json) : Except String Plan := do
  asPlan (← decodeProgram 256 j)

def checkDecoded (pj cj : Json) : Except String Bool :=
  match decodeProgram 256 pj, decodePlan cj with
  | .ok program, .ok plan => .ok (checkCertificate program plan)
  | .error e, _ => .error e
  | _, .error e => .error e

def decideDecoded (pj : Json) : Except String Bool :=
  match decodeProgram 256 pj with
  | .ok program => .ok (checkProgram program)
  | .error e => .error e

theorem decoded_decision_sound (pj : Json) (program : Program)
    (hp : decodeProgram 256 pj = .ok program)
    (checked : decideDecoded pj = .ok true) (kernel : Kernel)
    (public left right : Nat → Bool) :
    denote kernel public left program = denote kernel public right program := by
  apply checkProgram_sound program
  simpa [decideDecoded, hp] using checked

theorem decoded_certificate_sound (pj cj : Json) (program : Program) (plan : Plan)
    (hp : decodeProgram 256 pj = .ok program) (hc : decodePlan cj = .ok plan)
    (checked : checkDecoded pj cj = .ok true) (kernel : Kernel)
    (public left right : Nat → Bool) :
    denote kernel public left program = denote kernel public right program := by
  apply relational_sound program plan
  simpa [checkDecoded, hp, hc] using checked

#print axioms decoded_certificate_sound
#print axioms decoded_decision_sound

private structure TableEntry where
  contract : String
  request : String
  outcomes : List Outcome

private def table (j : Json) : Except String (List TableEntry) := do
  let entries ← (← j.getArr?).toList.mapM fun row => do
    let a ← fields row 3
    let outcomes ← (← a[2]!.getArr?).toList.mapM fun o => do
      let v ← fields o 4
      let numerator ← v[2]!.getInt?
      let denominator ← v[3]!.getNat?
      if numerator < 0 || denominator == 0 then throw "invalid probability"
      pure (Outcome.mk (← v[0]!.getStr?) (← v[1]!.getBool?)
        (Std.Internal.mkRat numerator denominator))
    if outcomes.foldl (fun sum o => sum + o.weight) (0 : Rat) != 1 then
      throw "kernel row probability mass must be one"
    pure (TableEntry.mk (← a[0]!.getStr?) (← a[1]!.getStr?) outcomes)
  let keys := entries.map fun e => (e.contract, e.request)
  if keys.eraseDups.length != keys.length then throw "duplicate kernel request"
  pure entries

private def tableKernel (entries : List TableEntry) : Kernel := fun contract request =>
  match entries.find? (fun e => e.contract == contract && e.request == request) with
  | some row => row.outcomes
  | none => match entries.find? (fun e => e.contract == contract && e.request == "*") with
    | some row => row.outcomes
    | none => []

-- Conservative operational limits for the executable, not proof premises.
private def pathBound (arity : Nat) : Program → Nat × Nat
  | .skip => (0, 1)
  | .call .. => (1, arity)
  | .seq a b =>
      let x := pathBound arity a
      let y := pathBound arity b
      (x.1 + y.1, min 100001 (x.2 * y.2))
  | .publicBranch _ a b | .secretBranch _ a b =>
      let x := pathBound arity a
      let y := pathBound arity b
      (max x.1 y.1, max x.2 y.2)
  | .retry n body =>
      let x := pathBound arity body
      (n*x.1, (List.range (n+1)).foldl (fun sum i => min 100001 (sum + x.2^i)) 0)

private def jsonEvent (e : Event) : Json :=
  toJson ([toJson e.contract, toJson e.input, toJson e.output, toJson e.failed] : List Json)

private def executeJson (program : Program) (j : Json) : Except String Json := do
  let entries ← table (← j.getObjVal? "kernels")
  let arity := entries.foldl (fun n row => max n row.outcomes.length) 1
  let limits := pathBound arity program
  if limits.1 > 128 || limits.2 > 100000 then throw "execution enumeration limit"
  let public ← (← (← j.getObjVal? "public").getArr?).mapM Json.getBool?
  let secret ← (← (← j.getObjVal? "secret").getArr?).mapM Json.getBool?
  let env ← (← (← j.getObjVal? "store").getArr?).mapM Json.getStr?
  let count ← (← j.getObjVal? "observe_slots").getNat?
  if count > 128 then throw "observed store limit"
  let runs := denote (tableKernel entries) (fun i => public[i]?.getD false)
    (fun i => secret[i]?.getD false) program (fun i => env[i]?.getD "")
  if runs.foldl (fun sum r => sum + r.weight) (0 : Rat) != 1 then
    throw "execution lost probability mass; missing request or invalid kernel"
  pure (toJson (runs.map fun r => Json.mkObj [
    ("trace", toJson (r.trace.map jsonEvent)), ("requests", toJson r.requests),
    ("store", toJson ((List.range count).map r.store)),
    ("p", toJson ([toJson r.weight.num, toJson r.weight.den] : List Json))]))

def checkBatch (j : Json) : Except String Json := do
  let cases ← j.getArr?
  let result ← cases.mapM fun row => do
    let programJson ← row.getObjVal? "program"
    let planJson ← row.getObjVal? "plan"
    let checked ← checkDecoded programJson planJson
    let program ← decodeProgram 256 programJson
    let evaluations ← (← (← row.getObjVal? "execute").getArr?).mapM (executeJson program)
    pure (Json.mkObj [("checked", Json.bool checked), ("executions", Json.arr evaluations)])
  pure (Json.arr result)

def decideBatch (j : Json) : Except String Json := do
  let cases ← j.getArr?
  let result ← cases.mapM fun row => do
    let programJson ← row.getObjVal? "program"
    let checked ← decideDecoded programJson
    let program ← decodeProgram 256 programJson
    let evaluations ← (← (← row.getObjVal? "execute").getArr?).mapM (executeJson program)
    pure (Json.mkObj [("checked", Json.bool checked), ("executions", Json.arr evaluations)])
  pure (Json.arr result)
end OrchLang.Dataflow

def main (args : List String) : IO UInt32 := do
  match args with
  | [path] | ["decide", path] =>
      let contents ← IO.FS.readFile path
      if contents.utf8ByteSize > 16000000 then
        (← IO.getStderr).putStrLn "batch byte limit"; return 2
      let checker := if args.length = 2 then OrchLang.Dataflow.decideBatch else OrchLang.Dataflow.checkBatch
      match Lean.Json.parse contents >>= checker with
      | .ok result => IO.println result.compress; pure 0
      | .error error => (← IO.getStderr).putStrLn error; pure 2
  | _ => (← IO.getStderr).putStrLn "usage: lean --run proof/DataflowCore.lean BATCH.json"; pure 2
