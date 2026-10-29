import AdmissionDomain

namespace OrchLang.Shape

/-- Arithmetic bridge from a checked finite token-piece bound to the size of a
    concatenated response. Native tokenization and decoding remain primitives. -/
theorem piece_lengths_budget (lengths : List Nat) (limit : Nat)
    (h : ∀ n ∈ lengths, n ≤ limit) : lengths.sum ≤ lengths.length * limit := by
  induction lengths with
  | nil => simp
  | cons head tail ih =>
      have hh := h head (by simp)
      have ht : ∀ n ∈ tail, n ≤ limit := fun n hn => h n (by simp [hn])
      simpa [List.sum_cons, List.length_cons, Nat.succ_mul, Nat.add_comm]
        using Nat.add_le_add hh (ih ht)

theorem response_piece_budget (lengths : List Nat) (limit cap : Nat)
    (h : ∀ n ∈ lengths, n ≤ limit) (hc : lengths.length ≤ cap) :
    lengths.sum ≤ cap * limit :=
  Nat.le_trans (piece_lengths_budget lengths limit h) (Nat.mul_le_mul_right limit hc)

#print axioms piece_lengths_budget
#print axioms response_piece_budget

/-- Tokenizer contract alpha = 1, delta = 0 as a segmentation property.
    If a tokenizer emits pieces that are each nonempty and whose concatenation
    is exactly the input byte string (no inserted BOS or other synthetic token),
    then the token count is at most the input's byte length. Byte-level BPE with
    automatic BOS disabled has this form: every merge covers at least one input
    byte, and special tokens parsed from template text render as their own
    nonempty literal bytes. The adapter checks both premises on every complete
    request before dispatch, so the inequality is monitored, not assumed. -/
theorem segmentation_count_le {α : Type} :
    ∀ pieces : List (List α), (∀ p ∈ pieces, p ≠ []) → pieces.length ≤ pieces.flatten.length
  | [], _ => by simp
  | p :: ps, h => by
      have hp : p ≠ [] := h p (by simp)
      have hps := segmentation_count_le ps (fun q hq => h q (by simp [hq]))
      have hlen : 1 ≤ p.length := by
        cases p with
        | nil => exact absurd rfl hp
        | cons _ _ => simp
      rw [List.flatten_cons, List.length_append, List.length_cons]
      omega

theorem tokenizer_alpha_one {α : Type} (pieces : List (List α)) (input : List α)
    (hseg : pieces.flatten = input) (hne : ∀ p ∈ pieces, p ≠ []) :
    pieces.length ≤ 1 * input.length + 0 := by
  rw [← hseg]; simpa using segmentation_count_le pieces hne

#print axioms tokenizer_alpha_one

end OrchLang.Shape
