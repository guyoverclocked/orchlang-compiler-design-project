import AdmissionDomain

namespace OrchLang.Shape

-- These executable checks exercise certificate arithmetic, including rejection.
-- Soundness is conditional on Envelope.Sound, as in the theorem; no concrete
-- tokenizer or output-expansion theorem is inferred from these examples.
private def testWorld : World where
  tok := fun _ r => r.length
  gen := fun _ r k _ => r.take k
  forced := fun _ r _ _ => r
  view := fun _ k r => r.take k
  padReq := fun _ _ r => r
  outTok := fun _ r => r.length
  toolFn := fun _ r => r
  dummyReq := "d"

private def testEnvelope : Envelope where
  size := String.length
  alpha := fun _ => 2
  overhead := fun _ => 3
  response := fun _ k => 4 * k
  tool := fun _ => 12
  context := fun _ => 256

private def first : Stmt := .call 0 1 "m" 4 (.var 0) (some (19,8))
private def second : Stmt := .call 1 2 "m" 8
  (.app (.lit "x") (.escape (.trim (.var 1)))) (some (69,8))
private def bounds : ValueBounds := [8,16,32]

#guard staticCertificate testWorld testEnvelope bounds (.seq first second)
#guard !staticCertificate testWorld testEnvelope bounds
  (.seq first (.call 1 2 "m" 8 (.var 1) (some (34,8))))
#guard !staticCertificate testWorld testEnvelope bounds
  (.call 0 1 "m" 9 (.var 0) (some (19,8)))
#guard !staticCertificate testWorld testEnvelope bounds
  (.call 0 1 "m" 4 (.var 0) (some (250,8)))
#guard !staticCertificate testWorld testEnvelope [8,15,32] first
#guard staticCertificate testWorld testEnvelope bounds
  (.ite (.eq 0 "s") (.seq first second) (.seq first second))
#guard staticCertificate testWorld testEnvelope bounds
  (.loop 5 (.eq 0 "done") (.seq first second) true)
#guard !staticCertificate testWorld testEnvelope bounds (.dummy "m" 0 8)
#guard !staticCertificate testWorld testEnvelope bounds
  (.loop 5 (.eq 0 "done") (.dummy "m" 0 8) true)
#guard staticCertificate testWorld testEnvelope bounds (.tool 1 "bounded" (.var 0))

end OrchLang.Shape
