import AdmissionDomain

/-! ### The UTF-8 byte measure discharges the structural envelope obligations

`Envelope.Sound` has six conjuncts. The first three concern only the text
measure and the expression operators of the core language. For the byte-bounded
adapter's measure, `String.utf8ByteSize`, they are theorems rather than
assumptions. Only the tokenizer, visible-response and tool-result bounds remain
contracts of the concrete serving adapter.
-/

namespace OrchLang.Shape

local notation "go" => String.utf8ByteSize.go

theorem go_cons (c : Char) (l : List Char) : go (c :: l) = go l + c.utf8Size := rfl

theorem go_append : ∀ a b : List Char, go (a ++ b) = go a + go b
  | [], b => by simp [String.utf8ByteSize.go]
  | c :: cs, b => by
      simp only [List.cons_append, go_cons, go_append cs b]; omega

theorem go_reverse : ∀ l : List Char, go l.reverse = go l
  | [] => rfl
  | c :: cs => by
      simp only [List.reverse_cons, go_append, go_reverse cs, go_cons]
      simp [String.utf8ByteSize.go]

theorem utf8_mk (l : List Char) : (String.mk l).utf8ByteSize = go l := rfl

theorem char_utf8Size_pos (c : Char) : 1 ≤ c.utf8Size := by
  unfold Char.utf8Size
  simp only
  split
  · decide
  · split
    · decide
    · split <;> decide

/-- Concatenation is additive, hence subadditive. -/
theorem utf8_append (a c : String) :
    (a ++ c).utf8ByteSize = a.utf8ByteSize + c.utf8ByteSize := by
  cases a with
  | mk l1 => cases c with
    | mk l2 => exact go_append l1 l2

theorem escapeChar_size (c : Char) : go (escapeChar c) ≤ 2 * c.utf8Size := by
  have hp := char_utf8Size_pos c
  unfold escapeChar
  split
  · simp [String.utf8ByteSize.go]; omega
  · split
    · have h92 : (Char.ofNat 92).utf8Size = 1 := by decide
      have hs : ('s' : Char).utf8Size = 1 := by decide
      simp [String.utf8ByteSize.go, h92, hs]; omega
    · simp [String.utf8ByteSize.go]; omega

theorem flatMap_escape_size : ∀ l : List Char, go (l.flatMap escapeChar) ≤ 2 * go l
  | [] => by simp [String.utf8ByteSize.go]
  | c :: cs => by
      have h1 := escapeChar_size c
      have h2 := flatMap_escape_size cs
      simp only [List.flatMap_cons, go_append, go_cons]
      omega

/-- Tool-argument escaping at most doubles the UTF-8 byte length. -/
theorem utf8_escape (a : String) :
    (escapeText a).utf8ByteSize ≤ 2 * a.utf8ByteSize := by
  cases a with
  | mk l => exact flatMap_escape_size l

theorem dropWhile_size (p : Char → Bool) : ∀ l : List Char, go (l.dropWhile p) ≤ go l
  | [] => by simp
  | c :: cs => by
      have ih := dropWhile_size p cs
      by_cases h : p c = true
      · simp [List.dropWhile_cons, h, go_cons]; omega
      · simp [List.dropWhile_cons, h]

/-- Template trimming never enlarges the UTF-8 byte length. -/
theorem utf8_trim (a : String) : (trimText a).utf8ByteSize ≤ a.utf8ByteSize := by
  cases a with
  | mk l =>
    unfold trimText
    rw [utf8_mk, go_reverse]
    exact Nat.le_trans (dropWhile_size _ _)
      (by rw [go_reverse]; exact dropWhile_size _ _)

/-- With the UTF-8 byte measure, `Envelope.Sound` reduces to its three serving
    contracts: the receiving tokenizer bound, the visible-response bound and the
    tool-result bound. -/
theorem utf8_envelope_sound (b : Envelope) (w : World)
    (hsize : b.size = String.utf8ByteSize)
    (htok : ∀ m r, w.tok m r ≤ b.alpha m * b.size r + b.overhead m)
    (hresp : ∀ m k T N r c, k ≤ N →
      b.size (w.view m k (w.forced m (w.padReq m T r) c N)) ≤ b.response m k)
    (htool : ∀ t r, b.size (w.toolFn t r) ≤ b.tool t) :
    b.Sound w := by
  refine ⟨?_, ?_, ?_, htok, hresp, htool⟩
  · intro a c; rw [hsize, utf8_append]; exact Nat.le_refl _
  · intro a; rw [hsize]; exact utf8_escape a
  · intro a; rw [hsize]; exact utf8_trim a

#print axioms utf8_envelope_sound

end OrchLang.Shape
