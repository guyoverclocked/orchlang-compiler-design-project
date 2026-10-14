(*
  Sequential returned-state refinement for the normalized request-node IR.

  This extends AtomicUpdates.v at the IR level.  It proves equality of node
  request histories and locals, equality of committed returned state with an
  eager result-register execution, and finite-prefix graph refinement (cycles
  included).  It does not prove that Python AST parsing, JSON lowering, the
  graph checker, or LangGraph itself implement this IR.
*)
From Coq Require Import List String Bool Arith.
From PublicationUpgrade Require Import AtomicUpdates.
Import ListNotations.
Open Scope string_scope.
Open Scope list_scope.

Definition store_equiv (left right : store) : Prop :=
  forall name, lookup name left = lookup name right.

Definition unique_write_fields (writes : updates) : Prop :=
  NoDup (map fst writes).

Definition unique_write_locals (writes : updates) : Prop :=
  NoDup (map snd writes).

Definition unique_call_locals (calls : list call) : Prop :=
  NoDup (map call_local calls).

Definition returns_are_calls (calls : list call) (writes : updates) : Prop :=
  forall field local, In (field, local) writes -> In local (map call_local calls).

Fixpoint returned_local (writes : updates) (field : key) : option key :=
  match writes with
  | [] => None
  | (candidate, local) :: rest =>
      if String.eqb field candidate then Some local else returned_local rest field
  end.

Fixpoint commit_returns (state : store) (writes : updates) (locals : store) : store :=
  match writes with
  | [] => state
  | (field, local) :: rest =>
      put field (lookup local locals) (commit_returns state rest locals)
  end.

Lemma returned_local_member :
  forall writes field local,
    returned_local writes field = Some local -> In (field, local) writes.
Proof.
  induction writes as [|[candidate value] rest IH]; intros field local Hfind;
    simpl in Hfind; [discriminate|].
  destruct (String.eqb field candidate) eqn:Heq.
  - inversion Hfind; subst. apply String.eqb_eq in Heq. subst. now left.
  - right. apply IH. exact Hfind.
Qed.

Lemma run_lowered_snapshot_irrelevant :
  forall omega calls writes snapshot1 snapshot2 state locals trace,
    run_lowered omega calls writes snapshot1 state locals trace =
    run_lowered omega calls writes snapshot2 state locals trace.
Proof.
  intros omega calls. induction calls as [|c rest IH]; intros; simpl; [reflexivity|].
  exact (IH writes snapshot1 snapshot2
    (state_after state writes c (omega trace (make_request state locals c)))
    (put (call_local c) (omega trace (make_request state locals c)) locals)
    (trace ++ [(make_request state locals c, omega trace (make_request state locals c))])).
Qed.

Lemma returned_local_in_unique_fields :
  forall writes field local,
    unique_write_fields writes ->
    In (field, local) writes ->
    returned_local writes field = Some local.
Proof.
  intros writes. induction writes as [|[candidate result] rest IH];
    intros field local Hunique Hin; [contradiction|].
  inversion Hunique as [|head tail Hnotin Htail]; subst.
  simpl in Hin. destruct Hin as [Heq | Hin].
  - inversion Heq; subst. simpl. now rewrite String.eqb_refl.
  - simpl. destruct (String.eqb field candidate) eqn:Heq.
    + apply String.eqb_eq in Heq. subst field.
      exfalso. apply Hnotin. apply in_map_iff.
      exists (candidate, local). split; [reflexivity|exact Hin].
    + now apply IH.
Qed.

Lemma commit_returns_lookup :
  forall state writes locals field,
    lookup field (commit_returns state writes locals) =
      match returned_local writes field with
      | Some local => lookup local locals
      | None => lookup field state
      end.
Proof.
  intros state writes. induction writes as [|[candidate local] rest IH];
    intros locals field; simpl.
  - reflexivity.
  - destruct (String.eqb field candidate) eqn:Heq.
    + apply String.eqb_eq in Heq. subst. reflexivity.
    + apply IH.
Qed.

Lemma field_for_local_in_unique :
  forall writes field local,
    unique_write_locals writes ->
    In (field, local) writes ->
    field_for_local writes local = Some field.
Proof.
  intros writes. induction writes as [|[candidate result] rest IH];
    intros field local Hunique Hin; [contradiction|].
  inversion Hunique as [|head tail Hnotin Htail]; subst.
  simpl in Hin. destruct Hin as [Heq | Hin].
  - inversion Heq; subst. simpl. now rewrite String.eqb_refl.
  - simpl. destruct (String.eqb local result) eqn:Heq.
    + apply String.eqb_eq in Heq. subst local.
      exfalso. apply Hnotin. apply in_map_iff.
      exists (field, result). split; [reflexivity|exact Hin].
    + apply IH; assumption.
Qed.

Lemma field_for_local_pair :
  forall writes local field,
    field_for_local writes local = Some field ->
    In (field, local) writes.
Proof.
  induction writes as [|[candidate result] rest IH]; intros local field H;
    simpl in H; [discriminate|].
  destruct (String.eqb local result) eqn:Heq.
  - inversion H; subst. apply String.eqb_eq in Heq. subst. now left.
  - right. now apply IH.
Qed.

Lemma unique_field_for_local :
  forall writes local1 local2 field,
    unique_write_fields writes ->
    field_for_local writes local1 = Some field ->
    field_for_local writes local2 = Some field ->
    local1 = local2.
Proof.
  intros writes local1 local2 field Hfields H1 H2.
  apply field_for_local_pair in H1.
  apply field_for_local_pair in H2.
  unfold unique_write_fields in Hfields.
  (* A field occurs at most once in [writes], so both pairs are the same. *)
  induction writes as [|[candidate result] rest IH]; simpl in *; [contradiction|].
  inversion Hfields as [|head tail Hnotin Htail]; subst.
  destruct H1 as [H1 | H1]; destruct H2 as [H2 | H2].
  - inversion H1; inversion H2; congruence.
  - inversion H1; subst.
    exfalso. apply Hnotin. apply in_map_iff.
    exists (field, local2). split; [reflexivity|exact H2].
  - inversion H2; subst.
    exfalso. apply Hnotin. apply in_map_iff.
    exists (field, local1). split; [reflexivity|exact H1].
  - now apply IH.
Qed.

Lemma state_after_lookup_written :
  forall state writes c response field local,
    field_for_local writes (call_local c) = Some local ->
    field = local ->
    lookup field (state_after state writes c response) = response.
Proof.
  intros state writes c response field local Hmap Heq. subst field.
  unfold state_after. rewrite Hmap. simpl. rewrite String.eqb_refl. reflexivity.
Qed.

Lemma state_after_lookup_unwritten :
  forall state writes c response field,
    field_for_local writes (call_local c) <> Some field ->
    lookup field (state_after state writes c response) = lookup field state.
Proof.
  intros state writes c response field Hmap.
  unfold state_after. destruct (field_for_local writes (call_local c)) as [written|]
    eqn:Hwritten; [|reflexivity].
  simpl. destruct (String.eqb field written) eqn:Heq; [|reflexivity].
  apply String.eqb_eq in Heq. subst written. contradiction.
Qed.

Lemma run_lowered_preserves_field :
  forall omega calls writes snapshot state locals trace field,
    (forall c, In c calls ->
      field_for_local writes (call_local c) <> Some field) ->
    lookup field (lower_state
      (run_lowered omega calls writes snapshot state locals trace)) = lookup field state.
Proof.
  intros omega calls. induction calls as [|c rest IH];
    intros writes snapshot state locals trace field Hnone; simpl; [reflexivity|].
  cbn [run_lowered].
  set (sent := make_request state locals c).
  set (response := omega trace sent).
  fold (state_after state writes c response).
  transitivity (lookup field (state_after state writes c response)).
  - apply IH. intros next Hin. apply Hnone. now right.
  - apply state_after_lookup_unwritten. apply Hnone. now left.
Qed.

Lemma run_lowered_preserves_local :
  forall omega calls writes snapshot state locals trace local,
    ~ In local (map call_local calls) ->
    lookup local (lower_locals
      (run_lowered omega calls writes snapshot state locals trace)) = lookup local locals.
Proof.
  intros omega calls. induction calls as [|c rest IH];
    intros writes snapshot state locals trace local Hnot; simpl; [reflexivity|].
  cbn [run_lowered].
  transitivity (lookup local
    (put (call_local c) (omega trace (make_request state locals c)) locals)).
  - apply IH. intro Hin. apply Hnot. simpl. now right.
  - simpl. destruct (String.eqb local (call_local c)) eqn:Heq; [|reflexivity].
    apply String.eqb_eq in Heq. subst. exfalso. apply Hnot. simpl. now left.
Qed.

Theorem eager_return_registers_match_locals :
  forall omega calls writes snapshot state locals trace field local,
    unique_write_fields writes ->
    unique_write_locals writes ->
    unique_call_locals calls ->
    In (field, local) writes ->
    In local (map call_local calls) ->
    lookup field (lower_state
      (run_lowered omega calls writes snapshot state locals trace)) =
    lookup local (lower_locals
      (run_lowered omega calls writes snapshot state locals trace)).
Proof.
  intros omega calls. induction calls as [|c rest IH];
    intros writes snapshot state locals trace field local Hfields Hresults Hcalls Hpair Hmember;
    [simpl in Hmember; contradiction|].
  inversion Hcalls as [|head tail Hnotin Htail]; subst.
  simpl in Hmember. destruct Hmember as [Heq | Hmember].
  - inversion Heq; subst local.
    assert (Hcurrent : field_for_local writes (call_local c) = Some field).
    { eapply field_for_local_in_unique; eauto. }
    assert (Hlocal_absent : ~ In (call_local c) (map call_local rest)).
    { intro Hin. apply Hnotin. exact Hin. }
    assert (Hfield_absent : forall next, In next rest ->
      field_for_local writes (call_local next) <> Some field).
    { intros next Hin Hwritten.
      pose proof (unique_field_for_local writes (call_local next) (call_local c) field
        Hfields Hwritten Hcurrent) as Heqlocal.
      apply Hlocal_absent. apply in_map_iff.
      exists next. split; [exact Heqlocal|exact Hin]. }
    cbn [run_lowered].
    set (sent := make_request state locals c).
    set (response := omega trace sent).
    fold (state_after state writes c response).
    transitivity response.
    + transitivity (lookup field (state_after state writes c response)).
      * apply run_lowered_preserves_field. exact Hfield_absent.
      * apply state_after_lookup_written with (local := field); [exact Hcurrent|reflexivity].
    + rewrite (run_lowered_preserves_local omega rest writes snapshot
        (state_after state writes c response) (put (call_local c) response locals)
        (trace ++ [(sent, response)]) (call_local c) Hlocal_absent).
      simpl. rewrite String.eqb_refl. reflexivity.
  - cbn [run_lowered].
    set (sent := make_request state locals c).
    set (response := omega trace sent).
    apply IH; try assumption.
Qed.

Theorem node_commit_refines_from :
  forall omega calls writes snapshot current trace,
    safe_after [] calls writes ->
    store_equiv snapshot current ->
    unique_write_fields writes ->
    unique_write_locals writes ->
    unique_call_locals calls ->
    returns_are_calls calls writes ->
    source_locals (run_source omega calls snapshot [] trace) =
      lower_locals (run_lowered omega calls writes snapshot current [] trace) /\
    source_history (run_source omega calls snapshot [] trace) =
      lower_history (run_lowered omega calls writes snapshot current [] trace) /\
    store_equiv
      (commit_returns snapshot writes
        (source_locals (run_source omega calls snapshot [] trace)))
      (lower_state (run_lowered omega calls writes snapshot current [] trace)).
Proof.
  intros omega calls writes snapshot current trace Hsafe Hinitial
    Hfields Hresults Hcalls Hcomplete.
  assert (Hagree : agrees_outside snapshot current []).
  { intros name Hnot. symmetry. apply Hinitial. }
  pose proof (atomic_update_request_trace_refines_from omega calls writes snapshot current
    [] trace [] Hsafe Hagree) as [Hlocals Hhistory].
  split; [exact Hlocals|]. split; [exact Hhistory|].
  unfold store_equiv. intros field.
  rewrite commit_returns_lookup.
  destruct (returned_local writes field) as [local|] eqn:Hreturned.
  - assert (Hpair : In (field, local) writes).
    { eapply returned_local_member. exact Hreturned. }
    assert (Hmember : In local (map call_local calls)).
    { eapply Hcomplete. exact Hpair. }
    rewrite Hlocals.
    symmetry. eapply eager_return_registers_match_locals; eauto.
  - rewrite (run_lowered_preserves_field omega calls writes snapshot current [] trace
      field).
    + apply Hinitial.
    + intros c Hin Hwritten.
      apply field_for_local_pair in Hwritten.
      pose proof (returned_local_in_unique_fields writes field (call_local c)
        Hfields Hwritten) as Hsome.
      rewrite Hreturned in Hsome. discriminate.
Qed.

(* This property records the frontend's lexical rule that a local-result
   argument may only name an earlier request assignment in the same node. *)
Definition local_argument_uses_prior (prior : list key) (arguments : list atom) : Prop :=
  Forall (fun item =>
    match item with
    | LocalResult local => In local prior
    | _ => True
    end) arguments.

Fixpoint local_reads_precede (prior : list key) (calls : list call) : Prop :=
  match calls with
  | [] => True
  | c :: rest =>
      local_argument_uses_prior prior (call_arguments c) /\
      local_reads_precede (prior ++ [call_local c]) rest
  end.

Definition bool_store := list (key * bool).

Fixpoint bool_lookup (name : key) (state : bool_store) : bool :=
  match state with
  | [] => false
  | (candidate, value) :: rest =>
      if String.eqb name candidate then value else bool_lookup name rest
  end.

Record workflow_state : Type := WorkflowState {
  text_fields : store;
  boolean_fields : bool_store
}.

Definition bool_store_equiv (left right : bool_store) : Prop :=
  forall name, bool_lookup name left = bool_lookup name right.

Definition workflow_state_equiv (left right : workflow_state) : Prop :=
  store_equiv (text_fields left) (text_fields right) /\
  bool_store_equiv (boolean_fields left) (boolean_fields right).

Inductive comparison : Type :=
| CLt | CLe | CGt | CGe | CEq | CNe.

Definition compare_nat (op : comparison) (actual limit : nat) : bool :=
  match op with
  | CLt => Nat.ltb actual limit
  | CLe => Nat.leb actual limit
  | CGt => Nat.ltb limit actual
  | CGe => Nat.leb limit actual
  | CEq => Nat.eqb actual limit
  | CNe => negb (Nat.eqb actual limit)
  end.

Inductive route_guard : Type :=
| BooleanInput (name : key)
| TokenCount (name : key) (op : comparison) (limit : nat).

Definition eval_route_guard (estimate : text -> nat) (state : workflow_state)
    (guard : route_guard) : bool :=
  match guard with
  | BooleanInput name => bool_lookup name (boolean_fields state)
  | TokenCount name op limit =>
      compare_nat op (estimate (lookup name (text_fields state))) limit
  end.

Inductive decision : Type :=
| Stop
| Goto (target : nat)
| Branch (guard : route_guard) (if_true if_false : nat).

Definition choose_next (estimate : text -> nat) (state : workflow_state)
    (next : decision) : option nat :=
  match next with
  | Stop => None
  | Goto target => Some target
  | Branch guard if_true if_false =>
      if eval_route_guard estimate state guard then Some if_true else Some if_false
  end.

Lemma choose_next_respects_state_equiv :
  forall estimate left right next,
    workflow_state_equiv left right ->
    choose_next estimate left next = choose_next estimate right next.
Proof.
  intros estimate left right next [Htext Hbool].
  destruct next as [|target|guard if_true if_false]; simpl; try reflexivity.
  destruct guard as [name|name op limit]; simpl.
  - rewrite Hbool. reflexivity.
  - rewrite Htext. reflexivity.
Qed.

Record workflow_node : Type := WorkflowNode {
  node_calls : list call;
  node_returns : updates;
  node_decision : decision;
  node_atomic_reads : safe_after [] node_calls node_returns;
  node_unique_fields : unique_write_fields node_returns;
  node_unique_results : unique_write_locals node_returns;
  node_unique_call_names : unique_call_locals node_calls;
  node_returns_from_calls : returns_are_calls node_calls node_returns;
  node_local_order : local_reads_precede [] node_calls
}.

Definition same_normalized_node (source target : workflow_node) : Prop :=
  node_calls source = node_calls target /\
  node_returns source = node_returns target /\
  node_decision source = node_decision target.

Definition paired_node := (workflow_node * workflow_node)%type.

Definition paired_node_matches (node_pair : paired_node) : Prop :=
  same_normalized_node (fst node_pair) (snd node_pair).

Definition paired_graph_matches (graph : list paired_node) : Prop :=
  Forall paired_node_matches graph.

Definition source_node_step (omega : oracle) (node : workflow_node)
    (state : workflow_state) (trace : history) : workflow_state * history :=
  let result := run_source omega (node_calls node) (text_fields state) [] trace in
  (WorkflowState
     (commit_returns (text_fields state) (node_returns node) (source_locals result))
     (boolean_fields state),
   source_history result).

Definition lowered_node_step (omega : oracle) (node : workflow_node)
    (state : workflow_state) (trace : history) : workflow_state * history :=
  let result := run_lowered omega (node_calls node) (node_returns node)
    (text_fields state) (text_fields state) [] trace in
  (WorkflowState (lower_state result) (boolean_fields state), lower_history result).

Lemma one_node_step_refines_from :
  forall omega node source_state lowered_state trace,
    workflow_state_equiv source_state lowered_state ->
    workflow_state_equiv
      (fst (source_node_step omega node source_state trace))
      (fst (lowered_node_step omega node lowered_state trace)) /\
    snd (source_node_step omega node source_state trace) =
      snd (lowered_node_step omega node lowered_state trace).
Proof.
  intros omega node source_state lowered_state trace [Htext Hbool].
  pose proof (node_commit_refines_from omega (node_calls node) (node_returns node)
    (text_fields source_state) (text_fields lowered_state) trace
    (node_atomic_reads node) Htext
    (node_unique_fields node) (node_unique_results node)
    (node_unique_call_names node) (node_returns_from_calls node))
    as [Hlocals [Htrace Hreturned]].
  unfold source_node_step, lowered_node_step. simpl.
  rewrite <- (run_lowered_snapshot_irrelevant omega (node_calls node)
    (node_returns node) (text_fields source_state) (text_fields lowered_state)
    (text_fields lowered_state) [] trace).
  split.
  - split.
    + exact Hreturned.
    + intros name. apply Hbool.
  - exact Htrace.
Qed.

Lemma paired_node_step_refines_from :
  forall omega source_node target_node source_state target_state trace,
    same_normalized_node source_node target_node ->
    workflow_state_equiv source_state target_state ->
    workflow_state_equiv
      (fst (source_node_step omega source_node source_state trace))
      (fst (lowered_node_step omega target_node target_state trace)) /\
    snd (source_node_step omega source_node source_state trace) =
      snd (lowered_node_step omega target_node target_state trace).
Proof.
  intros omega source_node target_node source_state target_state trace
    [Hcalls [Hreturns Hdecision]] [Htext Hbool].
  pose proof (node_commit_refines_from omega (node_calls source_node)
    (node_returns source_node) (text_fields source_state) (text_fields target_state)
    trace (node_atomic_reads source_node) Htext
    (node_unique_fields source_node) (node_unique_results source_node)
    (node_unique_call_names source_node) (node_returns_from_calls source_node))
    as [Hlocals [Htrace Hreturned]].
  unfold source_node_step, lowered_node_step. simpl.
  rewrite <- Hcalls, <- Hreturns.
  rewrite <- (run_lowered_snapshot_irrelevant omega (node_calls source_node)
    (node_returns source_node) (text_fields source_state) (text_fields target_state)
    (text_fields target_state) [] trace).
  split.
  - split.
    + exact Hreturned.
    + intros name. apply Hbool.
  - exact Htrace.
Qed.

Inductive graph_status : Type :=
| PrefixCutoff | GraphStopped | MissingTarget.

Record graph_result : Type := GraphResult {
  result_pc : nat;
  result_state : workflow_state;
  result_trace : history;
  result_status : graph_status
}.

Definition graph_result_equiv (left right : graph_result) : Prop :=
  result_status left = result_status right /\
  result_pc left = result_pc right /\
  result_trace left = result_trace right /\
  workflow_state_equiv (result_state left) (result_state right).

Fixpoint run_source_graph (fuel : nat) (nodes : list paired_node)
    (estimate : text -> nat) (omega : oracle) (pc : nat)
    (state : workflow_state) (trace : history) : graph_result :=
  match fuel with
  | 0 => GraphResult pc state trace PrefixCutoff
  | S rest =>
      match nth_error nodes pc with
      | None => GraphResult pc state trace MissingTarget
      | Some node_pair =>
          let output := source_node_step omega (fst node_pair) state trace in
          match choose_next estimate (fst output) (node_decision (fst node_pair)) with
          | None => GraphResult pc (fst output) (snd output) GraphStopped
          | Some target =>
              run_source_graph rest nodes estimate omega target (fst output) (snd output)
          end
      end
  end.

Fixpoint run_lowered_graph (fuel : nat) (nodes : list paired_node)
    (estimate : text -> nat) (omega : oracle) (pc : nat)
    (state : workflow_state) (trace : history) : graph_result :=
  match fuel with
  | 0 => GraphResult pc state trace PrefixCutoff
  | S rest =>
      match nth_error nodes pc with
      | None => GraphResult pc state trace MissingTarget
      | Some node_pair =>
          let output := lowered_node_step omega (snd node_pair) state trace in
          match choose_next estimate (fst output) (node_decision (snd node_pair)) with
          | None => GraphResult pc (fst output) (snd output) GraphStopped
          | Some target =>
              run_lowered_graph rest nodes estimate omega target (fst output) (snd output)
          end
      end
  end.

Theorem finite_prefix_graph_refines_including_cycles :
  forall fuel nodes estimate omega pc source_state lowered_state trace,
    paired_graph_matches nodes ->
    workflow_state_equiv source_state lowered_state ->
    graph_result_equiv
      (run_source_graph fuel nodes estimate omega pc source_state trace)
      (run_lowered_graph fuel nodes estimate omega pc lowered_state trace).
Proof.
  induction fuel as [|fuel IH]; intros nodes estimate omega pc source_state
    lowered_state trace Hgraph Hstate; cbn [run_source_graph run_lowered_graph].
  - destruct Hstate as [Htext Hbool].
    unfold graph_result_equiv. simpl. repeat split; try reflexivity; assumption.
  - destruct (nth_error nodes pc) as [node_pair|] eqn:Hnode.
    + assert (Hin : In node_pair nodes) by (apply nth_error_In with (n := pc); exact Hnode).
      pose proof Hgraph as Hgraph_all.
      unfold paired_graph_matches in Hgraph_all.
      pose proof (proj1 (Forall_forall paired_node_matches nodes)
        Hgraph_all) as Hgraph_at.
      specialize (Hgraph_at node_pair Hin).
      destruct node_pair as [source_node target_node]. simpl in Hgraph_at.
      pose proof (paired_node_step_refines_from omega source_node target_node
        source_state lowered_state trace Hgraph_at Hstate) as [Hstate' Htrace'].
      assert (Hroute :
        choose_next estimate (fst (source_node_step omega source_node source_state trace))
          (node_decision source_node) =
        choose_next estimate (fst (lowered_node_step omega target_node lowered_state trace))
          (node_decision target_node)).
      { destruct Hgraph_at as [_ [_ Hdecision]]. simpl in Hdecision.
        rewrite Hdecision.
        apply choose_next_respects_state_equiv. exact Hstate'. }
      fold (source_node_step omega source_node source_state trace).
      fold (lowered_node_step omega target_node lowered_state trace).
      cbn [fst snd].
      rewrite <- Hroute.
      destruct (choose_next estimate
        (fst (source_node_step omega source_node source_state trace))
        (node_decision source_node))
        as [target|] eqn:Hchoice; simpl.
      * unfold graph_result_equiv. simpl.
        pose proof (IH nodes estimate omega target
          (fst (source_node_step omega source_node source_state trace))
          (fst (lowered_node_step omega target_node lowered_state trace))
          (snd (source_node_step omega source_node source_state trace)) Hgraph Hstate') as Hrun.
        unfold source_node_step, lowered_node_step in Htrace'. simpl in Htrace'.
        rewrite <- Htrace'. unfold graph_result_equiv in Hrun. exact Hrun.
      * unfold source_node_step, lowered_node_step in Hstate', Htrace'.
        simpl in Hstate', Htrace'.
        unfold workflow_state_equiv in Hstate'. simpl in Hstate'.
        destruct Hstate' as [Htext' Hbool'].
        unfold graph_result_equiv. simpl. repeat split; try reflexivity; assumption.
    + destruct Hstate as [Htext Hbool].
      unfold graph_result_equiv. simpl. repeat split; try reflexivity; assumption.
Qed.
