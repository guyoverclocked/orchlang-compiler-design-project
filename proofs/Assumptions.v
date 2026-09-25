(* Each main theorem, and the axioms it depends on.  `make proofs` must print
   "Closed under the global context" for every one of them. *)
From OrchLang Require Import OrchLang.

Print Assumptions equiv_sound.
Print Assumptions resolve_exact.
Print Assumptions request_trace_noninterference.
Print Assumptions observers_agree.
Print Assumptions unary_bound.
Print Assumptions guaranteed_bound.
Print Assumptions size_blind.
