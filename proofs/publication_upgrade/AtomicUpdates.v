(*
  A small mechanized refinement result for the current source frontend's
  straight-line node fragment.  This is intentionally a theorem about the
  normalized node IR and its explicit side condition, not a proof that the
  Python AST parser constructs that IR correctly.

  The source semantics reads every state field from the node-entry snapshot
  and exposes returned state updates only after the node completes.  The
  lowered semantics writes the destination register at each request.  The
  `safe_after` premise states the extractor's atomic-update check: once a
  returned field has been written by an earlier call, later calls in that
  node do not read that field through `state[...]`.

  The extractor also guarantees that returned fields and their result locals
  are each unique. This file leaves that IR well-formedness fact outside the
  theorem and uses the first matching result local if an arbitrary `updates`
  list has repeats. The results below establish request-history and
  local-result agreement, not final returned-state equality or correctness of
  AST extraction.
*)
From Coq Require Import List String Bool.
Import ListNotations.
Open Scope string_scope.
Open Scope list_scope.

Definition key := string.
Definition text := string.
Definition store := list (key * text).

Fixpoint lookup (name : key) (s : store) : text :=
  match s with
  | [] => ""
  | (candidate, value) :: rest =>
      if String.eqb name candidate then value else lookup name rest
  end.

Definition put (name : key) (value : text) (s : store) : store :=
  (name, value) :: s.

Inductive atom : Type :=
| Literal (value : text)
| StateField (name : key)
| LocalResult (name : key).

Record request : Type := Request {
  request_model : string;
  request_template : text;
  request_arguments : list text
}.

Record call : Type := Call {
  call_local : key;
  call_model : string;
  call_template : text;
  call_arguments : list atom
}.

Definition updates := list (key * key). (* state field -> local result *)
Definition history := list (request * text).
Definition oracle := history -> request -> text.

Fixpoint eval_atoms (state locals : store) (arguments : list atom) : list text :=
  match arguments with
  | [] => []
  | Literal value :: rest => value :: eval_atoms state locals rest
  | StateField name :: rest => lookup name state :: eval_atoms state locals rest
  | LocalResult name :: rest => lookup name locals :: eval_atoms state locals rest
  end.

Definition make_request (state locals : store) (c : call) : request :=
  Request (call_model c) (call_template c)
    (eval_atoms state locals (call_arguments c)).

Fixpoint field_for_local (writes : updates) (local : key) : option key :=
  match writes with
  | [] => None
  | (field, result) :: rest =>
      if String.eqb local result then Some field else field_for_local rest local
  end.

Definition seen_after (seen : list key) (writes : updates) (c : call) : list key :=
  match field_for_local writes (call_local c) with
  | Some field => field :: seen
  | None => seen
  end.

Definition state_after (state : store) (writes : updates) (c : call)
    (response : text) : store :=
  match field_for_local writes (call_local c) with
  | Some field => put field response state
  | None => state
  end.

Definition read_safe (seen : list key) (arguments : list atom) : Prop :=
  Forall (fun item =>
    match item with
    | StateField name => ~ In name seen
    | _ => True
    end) arguments.

Fixpoint safe_after (seen : list key) (calls : list call) (writes : updates) : Prop :=
  match calls with
  | [] => True
  | c :: rest =>
      read_safe seen (call_arguments c) /\
      safe_after (seen_after seen writes c) rest writes
  end.

Definition agrees_outside (snapshot current : store) (seen : list key) : Prop :=
  forall name, ~ In name seen -> lookup name current = lookup name snapshot.

Record source_result : Type := SourceResult {
  source_locals : store;
  source_history : history
}.

Record lower_result : Type := LowerResult {
  lower_state : store;
  lower_locals : store;
  lower_history : history
}.

Fixpoint run_source (omega : oracle) (calls : list call) (snapshot locals : store)
  (trace : history) : source_result :=
  match calls with
  | [] => SourceResult locals trace
  | c :: rest =>
      let sent := make_request snapshot locals c in
      let response := omega trace sent in
      run_source omega rest snapshot (put (call_local c) response locals)
        (trace ++ [(sent, response)])
  end.

Fixpoint run_lowered (omega : oracle) (calls : list call) (writes : updates)
  (snapshot state locals : store) (trace : history) : lower_result :=
  match calls with
  | [] => LowerResult state locals trace
  | c :: rest =>
      let sent := make_request state locals c in
      let response := omega trace sent in
      run_lowered omega rest writes snapshot
        (state_after state writes c response)
        (put (call_local c) response locals)
        (trace ++ [(sent, response)])
  end.

Lemma eval_atoms_agree :
  forall arguments snapshot current locals seen,
    agrees_outside snapshot current seen ->
    read_safe seen arguments ->
    eval_atoms snapshot locals arguments = eval_atoms current locals arguments.
Proof.
  induction arguments as [|item rest IH]; intros snapshot current locals seen Hagree Hsafe;
    simpl in *; [reflexivity |].
  inversion Hsafe as [|item' rest' Hitem Hrest]; subst.
  destruct item as [value | name | name]; simpl in *.
  - f_equal. now apply IH with (seen := seen).
  - f_equal.
    + symmetry. apply Hagree. exact Hitem.
    + now apply IH with (seen := seen).
  - f_equal. now apply IH with (seen := seen).
Qed.

Lemma request_agree :
  forall c snapshot current locals seen,
    agrees_outside snapshot current seen ->
    read_safe seen (call_arguments c) ->
    make_request snapshot locals c = make_request current locals c.
Proof.
  intros [local model template arguments] snapshot current locals seen Hagree Hsafe.
  unfold make_request. simpl. f_equal.
  now apply eval_atoms_agree with (seen := seen).
Qed.

Lemma agrees_after_put :
  forall snapshot current seen field value,
    agrees_outside snapshot current seen ->
    agrees_outside snapshot (put field value current) (field :: seen).
Proof.
  intros snapshot current seen field value Hagree name Hnot.
  assert (Hneq : name <> field).
  { intro Heq. subst name. apply Hnot. now left. }
  change (lookup name ((field, value) :: current) = lookup name snapshot).
  simpl. destruct (String.eqb name field) eqn:Hsame.
  - apply String.eqb_eq in Hsame. contradiction.
  - apply Hagree. intro Hin. apply Hnot. now right.
Qed.

Lemma agrees_after_call :
  forall snapshot current seen writes c response,
    agrees_outside snapshot current seen ->
    agrees_outside snapshot (state_after current writes c response)
      (seen_after seen writes c).
Proof.
  intros snapshot current seen writes c response Hagree.
  unfold state_after, seen_after.
  destruct (field_for_local writes (call_local c)) as [field |] eqn:Hfield;
    [apply agrees_after_put |]; assumption.
Qed.

Theorem atomic_update_request_trace_refines_from :
  forall omega calls,
    forall writes snapshot current locals trace seen,
      safe_after seen calls writes ->
      agrees_outside snapshot current seen ->
      source_locals (run_source omega calls snapshot locals trace) =
        lower_locals (run_lowered omega calls writes snapshot current locals trace) /\
      source_history (run_source omega calls snapshot locals trace) =
        lower_history (run_lowered omega calls writes snapshot current locals trace).
Proof.
  intros omega calls. induction calls as [|c rest IH].
  - intros writes snapshot current locals trace seen Hsafe Hagree.
    simpl. auto.
  - intros writes snapshot current locals trace seen Hsafe Hagree.
    simpl in Hsafe. destruct Hsafe as [Hread Hrest].
    pose proof (request_agree c snapshot current locals seen Hagree Hread) as Hrequest.
    cbn [run_source run_lowered].
    rewrite <- Hrequest.
    set (sent := make_request snapshot locals c).
    set (response := omega trace sent).
    specialize (IH writes snapshot (state_after current writes c response)
      (put (call_local c) response locals) (trace ++ [(sent, response)])
      (seen_after seen writes c) Hrest).
    assert (Hnext : agrees_outside snapshot (state_after current writes c response)
      (seen_after seen writes c)).
    { apply agrees_after_call. exact Hagree. }
    specialize (IH Hnext).
    exact IH.
Qed.

Theorem atomic_update_request_trace_refines :
  forall omega calls writes snapshot locals trace,
    safe_after [] calls writes ->
    source_locals (run_source omega calls snapshot locals trace) =
      lower_locals (run_lowered omega calls writes snapshot snapshot locals trace) /\
    source_history (run_source omega calls snapshot locals trace) =
      lower_history (run_lowered omega calls writes snapshot snapshot locals trace).
Proof.
  intros omega calls writes snapshot locals trace Hsafe.
  eapply atomic_update_request_trace_refines_from; [exact Hsafe |].
  intros name Hnot. reflexivity.
Qed.
