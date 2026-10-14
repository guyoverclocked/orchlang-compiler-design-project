(* Small executable witnesses for conditions used by SequentialUpdates.v. *)
From Coq Require Import List String.
From PublicationUpgrade Require Import AtomicUpdates.
From SCPStrengthening Require Import SequentialUpdates.
Import ListNotations.
Open Scope string_scope.
Open Scope list_scope.

Definition ce_oracle : oracle :=
  fun _ sent =>
    if String.eqb (request_template sent) "make" then "new" else "ok".

Definition ce_make : call := Call "draft_local" "m" "make" [Literal "x"].
Definition ce_read_old : call :=
  Call "answer_local" "m" "consume" [StateField "draft"].
Definition ce_snapshot_calls : list call := [ce_make; ce_read_old].
Definition ce_snapshot_writes : updates := [("draft", "draft_local")].
Definition ce_initial : store := [("draft", "old"); ("answer", "old answer")].

Example read_after_return_write_breaks_trace_agreement :
  ~ safe_after [] ce_snapshot_calls ce_snapshot_writes /\
  source_history (run_source ce_oracle ce_snapshot_calls ce_initial [] []) <>
  lower_history
    (run_lowered ce_oracle ce_snapshot_calls ce_snapshot_writes
      ce_initial ce_initial [] []).
Proof.
  split.
  - intro Hsafe.
    unfold safe_after, read_safe in Hsafe. simpl in Hsafe.
    destruct Hsafe as [_ [Hbad _]].
    inversion Hbad as [|item rest Hnot _]; subst.
    apply Hnot. simpl. left. reflexivity.
  - vm_compute. discriminate.
Qed.

Definition ce_single_call : list call :=
  [Call "result_local" "m" "make" [Literal "x"]].
Definition ce_duplicate_local_writes : updates :=
  [("draft", "result_local"); ("answer", "result_local")].

Example reusing_one_return_local_loses_one_target_field :
  lookup "answer"
    (commit_returns ce_initial ce_duplicate_local_writes
      (source_locals (run_source ce_oracle ce_single_call ce_initial [] []))) <>
  lookup "answer"
    (lower_state
      (run_lowered ce_oracle ce_single_call ce_duplicate_local_writes
        ce_initial ce_initial [] [])).
Proof.
  vm_compute. discriminate.
Qed.

Definition ce_two_calls : list call :=
  [Call "first_local" "m" "first" [Literal "x"];
   Call "second_local" "m" "second" [Literal "x"]].
Definition ce_duplicate_field_writes : updates :=
  [("draft", "first_local"); ("draft", "second_local")].
Definition ce_two_oracle : oracle :=
  fun _ sent =>
    if String.eqb (request_template sent) "first" then "one" else "two".

Example duplicate_return_field_makes_commit_order_observable :
  lookup "draft"
    (commit_returns ce_initial ce_duplicate_field_writes
      (source_locals (run_source ce_two_oracle ce_two_calls ce_initial [] []))) <>
  lookup "draft"
    (lower_state
      (run_lowered ce_two_oracle ce_two_calls ce_duplicate_field_writes
        ce_initial ce_initial [] [])).
Proof.
  vm_compute. discriminate.
Qed.

Definition empty_cycle_node : workflow_node.
Proof.
  refine (WorkflowNode [] [] (Goto 0) _ _ _ _ _ _).
  - simpl. exact I.
  - constructor.
  - constructor.
  - constructor.
  - intros field local Hin. contradiction.
  - exact I.
Defined.

Example finite_prefix_cycle_reaches_cutoff :
  result_status
    (run_source_graph 4 [(empty_cycle_node, empty_cycle_node)] (fun _ => 0) ce_oracle 0
      (WorkflowState [] []) []) = PrefixCutoff.
Proof.
  vm_compute. reflexivity.
Qed.

Example finite_prefix_cycle_refines :
  graph_result_equiv
    (run_source_graph 4 [(empty_cycle_node, empty_cycle_node)] (fun _ => 0) ce_oracle 0
      (WorkflowState [] []) [])
    (run_lowered_graph 4 [(empty_cycle_node, empty_cycle_node)] (fun _ => 0) ce_oracle 0
      (WorkflowState [] []) []).
Proof.
  apply finite_prefix_graph_refines_including_cycles.
  - constructor.
    + unfold paired_node_matches, same_normalized_node. simpl.
      repeat split; reflexivity.
    + constructor.
  - split; intros name; reflexivity.
Qed.
