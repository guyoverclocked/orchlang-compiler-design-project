import AdmissionDomain

namespace OrchLang.Shape
open Lean

private def pairs (j : Json) : Except String (List (String × Nat)) := do
  (← j.getArr?).toList.mapM fun row => do
    let a ← row.getArr?
    if a.size != 2 then throw "expected name/bound pair"
    pure ((← a[0]!.getStr?), (← a[1]!.getNat?))

private def lookup (rows : List (String × Nat)) (name : String) : Nat :=
  ((rows.find? (fun row => row.1 == name)).map Prod.snd).getD 0

/-- Evaluate the theorem's checker on a real serialized candidate and explicit
    adapter bounds. This does not prove the native tokenizer implementation. -/
def checkAdmissionJson (j : Json) : Except String Json := do
  let p ← decodeStmt 4096 (← j.getObjVal? "program")
  let v ← (← (← j.getObjVal? "bounds").getArr?).toList.mapM Json.getNat?
  let tools ← pairs (← j.getObjVal? "tools")
  let dummy ← pairs (← j.getObjVal? "dummy_tokens")
  let multiplier ← j.getObjValAs? Nat "response_bytes_per_token"
  let context ← j.getObjValAs? Nat "context"
  let alpha ← j.getObjValAs? Nat "alpha"
  let delta ← j.getObjValAs? Nat "delta"
  let b : Envelope := {
    size := String.utf8ByteSize, alpha := fun _ => alpha, overhead := fun _ => delta,
    response := fun _ k => multiplier * k, tool := lookup tools,
    context := fun _ => context }
  -- Only tok m dummyReq is consulted by staticCertificate. Its values are
  -- supplied from the concrete adapter's separately checked canonical dummy.
  let w : World := {
    tok := fun m _ => lookup dummy m, gen := fun _ _ _ _ => "",
    forced := fun _ _ _ _ => "", view := fun _ _ _ => "",
    padReq := fun _ _ r => r, outTok := fun _ _ => 0,
    toolFn := fun _ _ => "", dummyReq := "." }
  pure (Json.mkObj [("accepted", Json.bool (staticCertificate w b v p)),
                    ("has_fixed_shape", Json.bool (shape p).isSome),
                    ("unit", Json.str "UTF-8 bytes"),
                    ("native_adapter_verified", Json.bool false)])

end OrchLang.Shape

#eval (do
  match ← IO.getEnv "ORCHLANG_ADMISSION_INPUT" with
  | none => pure ()
  | some path =>
      let contents ← IO.FS.readFile path
      let result := do
        let j ← Lean.Json.parse contents
        (← j.getArr?).mapM OrchLang.Shape.checkAdmissionJson
      match result with
      | .ok rows => IO.println (Lean.Json.arr rows).compress
      | .error error => throw (IO.userError error) : IO Unit)
