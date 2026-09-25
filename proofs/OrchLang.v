(* OrchLang core calculus: request-trace noninterference, the unary bound,
   and size-blindness.

   This file mechanises, for the core calculus of docs/FORMAL_MODEL.md section 1,

     - Lemma 2 (equiv_sound): two programs related by the request-equivalence
       judgment produce identical histories on every tape, for every provider,
       validator and keying scheme that is a function of the history and the
       request, and leave related stores.
     - Resolution (resolve_exact): resolving the secret guards of a program by
       the outcomes a store actually gives does not change what it does.
     - Theorem 1 (request_trace_noninterference, observers_agree): a program
       whose resolutions under two stores' outcome vectors are related, from
       the public variables on which the stores agree, gives the two stores
       the same history, so every observer of the history agrees.
     - Theorem 5 (unary_bound, guaranteed_bound): output tokens and billed
       input tokens are bounded by the analysis's figures, under a tokenizer
       contract tokens <= kappa * bytes + sigma plus envelope overhead, a
       bound on response bytes, and declared byte bounds on variables.
     - Theorem 6 (size_blind): an analysis that sees text constants only
       through a size measure mu, and is sound for total output tokens against
       every deterministic provider respecting the caps, rejects every program
       with a feasible secret branch whose then-arm calls a model with a
       positive cap on a request containing a text constant with a fresh twin
       -- whatever the else-arm is, including the same code.

   Everything about the world is a Section variable: the provider Pi, the
   retry validator V, the keying schemes, the tape, the guard predicates, the
   tokenizer.  Nothing is assumed about Pi or V in Theorems 1 and 6 (Theorem 6
   quantifies over them); Theorem 5 assumes only the caps and contracts it
   names.

   Modelling choices, stated plainly:
     - Strings are Coq strings, sequences of 8-bit characters, so String.length
       is a length in bytes.
     - The store is flat.  OrchLang's block scoping appears as the freshness
       side conditions of the judgment (a call may only bind a variable not yet
       related), which the implementation meets by giving every binding a
       unique identity.
     - Literal arguments and template text are both static text; the judgment
       compares requests after merging adjacent static text, as the
       implementation does, and merging is proved to preserve the request.
     - The judgment is a relation; the implementation computes a signature per
       outcome vector and compares signatures for equality.  That equal
       signatures give a derivation of the judgment is argued on paper
       (docs/FORMAL_MODEL.md section 5), not here.
     - Randomness is a tape indexed by keys.  That a fresh keying scheme gives
       each execution its correct distribution (Lemma 1) is not mechanised.

   The C++ implementation is not verified against this model. *)

From Coq Require Import Ascii String List Arith Lia Bool.
Import ListNotations.
Open Scope string_scope.
Open Scope list_scope.

(* ------------------------------------------------------------------ syntax *)

Definition var := string.
Definition model := string.

(* A piece of a request: template text, a literal argument, or a variable. *)
Inductive piece : Type :=
| PText (t : string)
| PLit (t : string)
| PVar (x : var).

(* A guard applies a named predicate to a variable's value. *)
Record guard : Type := mkGuard { gpred : nat; gvar : var }.

Inductive stmt : Type :=
| SNop : stmt
| SCall : var -> model -> list piece -> stmt
| SIf : guard -> block -> block -> stmt
| SRetry : nat -> block -> stmt
with block : Type :=
| BNil : block
| BCons : stmt -> block -> block.

Scheme stmt_mut := Induction for stmt Sort Prop
with block_mut := Induction for block Sort Prop.
Combined Scheme syntax_mut from stmt_mut, block_mut.

Fixpoint app_block (b1 b2 : block) : block :=
  match b1 with
  | BNil => b2
  | BCons s rest => BCons s (app_block rest b2)
  end.

(* ------------------------------------------------------------------ events *)

Inductive event : Type :=
| EvCall (m : model) (q : string) (resp : string) (o : nat)
| EvAttempt (ok : bool).

Definition history := list event.
Definition store := var -> string.

Definition update (s : store) (x : var) (v : string) : store :=
  fun y => if String.eqb x y then v else s y.

(* ---------------------------------------------------------------- strings *)

Notation sapp := String.append.

Lemma sapp_assoc : forall a b c : string, sapp (sapp a b) c = sapp a (sapp b c).
Proof. induction a; intros; simpl; [reflexivity | now rewrite IHa]. Qed.

Lemma sapp_length : forall a b : string,
    String.length (sapp a b) = String.length a + String.length b.
Proof. induction a; intros; simpl; [reflexivity | now rewrite IHa]. Qed.

(* -------------------------------------------------------------- semantics *)

Section Semantics.

  Variable Key Draw : Type.
  (* Guard predicates, by name. *)
  Variable interp : nat -> string -> bool.
  (* Keying schemes: any function of the history so far and the request (for a
     call), or of the history and the attempt's transcript (for a retry
     decision).  The global, per-model and per-request schemes are all of this
     form. *)
  Variable key_call : history -> model -> string -> Key.
  Variable key_retry : history -> history -> Key.
  Variable tape : Key -> Draw.
  (* The provider: response text and reported output tokens.  Arbitrary. *)
  Variable Pi : model -> string -> Draw -> string * nat.
  (* The retry validator: arbitrary. *)
  Variable V : history -> Draw -> bool.

  Definition eval_piece (s : store) (p : piece) : string :=
    match p with
    | PText t => t
    | PLit t => t
    | PVar x => s x
    end.

  Fixpoint eval_pieces (s : store) (ps : list piece) : string :=
    match ps with
    | [] => ""
    | p :: rest => sapp (eval_piece s p) (eval_pieces s rest)
    end.

  Definition eval_guard (s : store) (g : guard) : bool := interp (gpred g) (s (gvar g)).

  (* Up to n attempts of a body that maps a history to its extension.  An
     attempt's transcript is what it appended; the decision reads that
     transcript and a draw keyed by it. *)
  Fixpoint retry_loop (body : store -> history -> store * history) (n : nat)
           (s : store) (h : history) : store * history :=
    match n with
    | 0 => (s, h)
    | S n' =>
        let '(s1, h1) := body s h in
        let t := skipn (length h) h1 in
        let ok := V t (tape (key_retry h t)) in
        let h2 := h1 ++ [EvAttempt ok] in
        if ok then (s1, h2) else retry_loop body n' s1 h2
    end.

  Fixpoint exec_stmt (st : stmt) (s : store) (h : history) {struct st} : store * history :=
    match st with
    | SNop => (s, h)
    | SCall x m ps =>
        let q := eval_pieces s ps in
        let '(resp, o) := Pi m q (tape (key_call h m q)) in
        (update s x resp, h ++ [EvCall m q resp o])
    | SIf g b1 b2 => if eval_guard s g then exec_block b1 s h else exec_block b2 s h
    | SRetry n b => retry_loop (exec_block b) n s h
    end
  with exec_block (b : block) (s : store) (h : history) {struct b} : store * history :=
    match b with
    | BNil => (s, h)
    | BCons st rest => let '(s1, h1) := exec_stmt st s h in exec_block rest s1 h1
    end.

  Lemma exec_app : forall b1 b2 s h,
      exec_block (app_block b1 b2) s h =
      let '(s1, h1) := exec_block b1 s h in exec_block b2 s1 h1.
  Proof.
    induction b1 as [| st rest IH]; intros b2 s h; simpl.
    - reflexivity.
    - destruct (exec_stmt st s h) as [s1 h1]. apply IH.
  Qed.

  (* Execution only ever appends to the history.  Stated for any property E
     of the appended events closed under concatenation and any store
     invariant Q, so that later sections can reuse it. *)
  Lemma retry_loop_extends : forall (Q : store -> Prop) (E : history -> Prop) body n,
      E [] -> (forall ok, E [EvAttempt ok]) -> (forall t1 t2, E t1 -> E t2 -> E (t1 ++ t2)) ->
      (forall s h, Q s -> exists t, snd (body s h) = h ++ t /\ E t /\ Q (fst (body s h))) ->
      forall s h, Q s ->
        exists t, snd (retry_loop body n s h) = h ++ t /\ E t /\ Q (fst (retry_loop body n s h)).
  Proof.
    intros Q E body n E0 E1 Eapp Hbody. induction n as [| n IH]; intros s h Hs; simpl.
    - exists []. rewrite app_nil_r. auto.
    - destruct (Hbody s h Hs) as [t1 [Ht1 [He1 Hs1]]].
      destruct (body s h) as [s1 h1]. simpl in *. subst h1.
      rewrite skipn_app, Nat.sub_diag, skipn_all. simpl.
      destruct (V t1 _).
      + exists (t1 ++ [EvAttempt true]). rewrite app_assoc. auto.
      + destruct (IH s1 ((h ++ t1) ++ [EvAttempt false]) Hs1) as [t2 [Ht2 [He2 Hs2]]].
        exists (t1 ++ EvAttempt false :: t2). split; [| split; [| assumption]].
        * rewrite Ht2. rewrite <- !app_assoc. reflexivity.
        * apply Eapp; [assumption |]. apply (Eapp [EvAttempt false] t2); auto.
  Qed.

  Lemma exec_extends :
    (forall st s h, exists t, snd (exec_stmt st s h) = h ++ t) /\
    (forall b s h, exists t, snd (exec_block b s h) = h ++ t).
  Proof.
    apply (syntax_mut
      (fun st => forall s h, exists t, snd (exec_stmt st s h) = h ++ t)
      (fun b => forall s h, exists t, snd (exec_block b s h) = h ++ t)).
    - intros s h. exists []. now rewrite app_nil_r.
    - intros x m ps s h. simpl. destruct (Pi m _ _). now eexists.
    - intros g b1 IH1 b2 IH2 s h. simpl. destruct (eval_guard s g); auto.
    - intros n b IH s h. simpl.
      destruct (retry_loop_extends (fun _ => True) (fun _ => True) (exec_block b) n)
        with (s := s) (h := h) as [t [Ht _]]; auto.
      + intros a h' _. destruct (IH a h') as [t Ht]. eauto.
      + eauto.
    - intros s h. exists []. now rewrite app_nil_r.
    - intros st IHs rest IHr s h. simpl. destruct (IHs s h) as [t1 Ht1].
      destruct (exec_stmt st s h) as [s1 h1]. simpl in Ht1. subst h1.
      destruct (IHr s1 (h ++ t1)) as [t2 Ht2]. exists (t1 ++ t2). now rewrite Ht2, app_assoc.
  Qed.

  (* ------------------------------------------------ merging static text *)

  (* Adjacent static text is one run of characters to the provider. *)
  Fixpoint merge (ps : list piece) : list piece :=
    match ps with
    | [] => []
    | PVar x :: rest => PVar x :: merge rest
    | PText t :: rest =>
        match merge rest with
        | PText u :: rest' => PText (sapp t u) :: rest'
        | rest' => PText t :: rest'
        end
    | PLit t :: rest =>
        match merge rest with
        | PText u :: rest' => PText (sapp t u) :: rest'
        | rest' => PText t :: rest'
        end
    end.

  Lemma merge_eval : forall s ps, eval_pieces s (merge ps) = eval_pieces s ps.
  Proof.
    intros s ps. induction ps as [| p rest IH]; [reflexivity |].
    destruct p as [t | t | x]; simpl.
    - destruct (merge rest) as [| [u | u | y] rest'] eqn:E; simpl in *;
        rewrite <- IH; try reflexivity.
      now rewrite sapp_assoc.
    - destruct (merge rest) as [| [u | u | y] rest'] eqn:E; simpl in *;
        rewrite <- IH; try reflexivity.
      now rewrite sapp_assoc.
    - now rewrite IH.
  Qed.

  (* ------------------------------------ the request-equivalence judgment *)

  (* A relation between the variables of two programs whose values agree. *)
  Definition rel := list (var * var).

  Definition related (G : rel) (s1 s2 : store) : Prop :=
    forall x y, In (x, y) G -> s1 x = s2 y.

  Inductive pequiv (G : rel) : piece -> piece -> Prop :=
  | PQText : forall t, pequiv G (PText t) (PText t)
  | PQVar : forall x y, In (x, y) G -> pequiv G (PVar x) (PVar y).

  Inductive sequiv : rel -> stmt -> stmt -> rel -> Prop :=
  | SQCall : forall G x y m ps1 ps2,
      Forall2 (pequiv G) (merge ps1) (merge ps2) ->
      ~ In x (map fst G) -> ~ In y (map snd G) ->
      sequiv G (SCall x m ps1) (SCall y m ps2) ((x, y) :: G)
  | SQIf : forall G g1 g2 b1 b2 d1 d2 G1 G2,
      gpred g1 = gpred g2 -> In (gvar g1, gvar g2) G ->
      bequiv G b1 d1 G1 -> bequiv G b2 d2 G2 ->
      sequiv G (SIf g1 b1 b2) (SIf g2 d1 d2) G
  | SQRetry : forall G n b d G',
      bequiv G b d G' -> sequiv G (SRetry n b) (SRetry n d) G
  with bequiv : rel -> block -> block -> rel -> Prop :=
  | BQNil : forall G, bequiv G BNil BNil G
  | BQNopL : forall G b d G', bequiv G b d G' -> bequiv G (BCons SNop b) d G'
  | BQNopR : forall G b d G', bequiv G b d G' -> bequiv G b (BCons SNop d) G'
  | BQCons : forall G G1 G2 s1 s2 b d,
      sequiv G s1 s2 G1 -> bequiv G1 b d G2 -> bequiv G (BCons s1 b) (BCons s2 d) G2.

  Scheme sequiv_mut := Induction for sequiv Sort Prop
  with bequiv_mut := Induction for bequiv Sort Prop.
  Combined Scheme equiv_mut from sequiv_mut, bequiv_mut.

  Lemma pieces_equiv_eval : forall G s1 s2 ps1 ps2,
      related G s1 s2 -> Forall2 (pequiv G) ps1 ps2 ->
      eval_pieces s1 ps1 = eval_pieces s2 ps2.
  Proof.
    intros G s1 s2 ps1 ps2 Hrel Hall.
    induction Hall as [| p1 p2 rest1 rest2 Hp Hrest IH]; [reflexivity |].
    simpl. rewrite IH. inversion Hp; subst; simpl.
    - reflexivity.
    - f_equal. now apply Hrel.
  Qed.

  (* Every judgment extends its input relation. *)
  Lemma equiv_extends :
    (forall G st1 st2 G', sequiv G st1 st2 G' -> exists E, G' = E ++ G) /\
    (forall G b1 b2 G', bequiv G b1 b2 G' -> exists E, G' = E ++ G).
  Proof.
    apply (equiv_mut
      (fun G _ _ G' _ => exists E, G' = E ++ G)
      (fun G _ _ G' _ => exists E, G' = E ++ G)).
    all: intros; try (exists []; reflexivity).
    - exists [(x, y)]. reflexivity.
    - assumption.
    - assumption.
    - destruct H as [E1 ->]. destruct H0 as [E2 ->]. exists (E2 ++ E1). now rewrite app_assoc.
  Qed.

  Lemma related_weaken : forall E G s1 s2, related (E ++ G) s1 s2 -> related G s1 s2.
  Proof. intros E G s1 s2 H x y Hin. apply H. apply in_or_app. now right. Qed.

  (* Retry loops over bodies that agree pointwise, from related stores, agree. *)
  Lemma retry_loop_agree : forall (G : rel) body1 body2 n,
      (forall s1 s2 h, related G s1 s2 ->
         snd (body1 s1 h) = snd (body2 s2 h) /\ related G (fst (body1 s1 h)) (fst (body2 s2 h))) ->
      forall s1 s2 h, related G s1 s2 ->
        snd (retry_loop body1 n s1 h) = snd (retry_loop body2 n s2 h) /\
        related G (fst (retry_loop body1 n s1 h)) (fst (retry_loop body2 n s2 h)).
  Proof.
    intros G body1 body2 n Hbody. induction n as [| n IH]; intros s1 s2 h Hrel; simpl.
    - split; [reflexivity | assumption].
    - specialize (Hbody s1 s2 h Hrel).
      destruct (body1 s1 h) as [a1 h1] eqn:E1. destruct (body2 s2 h) as [a2 h2] eqn:E2.
      simpl in Hbody. destruct Hbody as [Hh Hr]. subst h2.
      destruct (V (skipn (length h) h1) (tape (key_retry h (skipn (length h) h1)))).
      + simpl. split; [reflexivity | assumption].
      + apply IH. assumption.
  Qed.

  (* Lemma 2: related programs from related stores produce the same history,
     and leave related stores. *)
  Theorem equiv_sound :
    (forall G st1 st2 G', sequiv G st1 st2 G' ->
       forall s1 s2 h, related G s1 s2 ->
         snd (exec_stmt st1 s1 h) = snd (exec_stmt st2 s2 h) /\
         related G' (fst (exec_stmt st1 s1 h)) (fst (exec_stmt st2 s2 h))) /\
    (forall G b1 b2 G', bequiv G b1 b2 G' ->
       forall s1 s2 h, related G s1 s2 ->
         snd (exec_block b1 s1 h) = snd (exec_block b2 s2 h) /\
         related G' (fst (exec_block b1 s1 h)) (fst (exec_block b2 s2 h))).
  Proof.
    apply (equiv_mut
      (fun G st1 st2 G' _ => forall s1 s2 h, related G s1 s2 ->
         snd (exec_stmt st1 s1 h) = snd (exec_stmt st2 s2 h) /\
         related G' (fst (exec_stmt st1 s1 h)) (fst (exec_stmt st2 s2 h)))
      (fun G b1 b2 G' _ => forall s1 s2 h, related G s1 s2 ->
         snd (exec_block b1 s1 h) = snd (exec_block b2 s2 h) /\
         related G' (fst (exec_block b1 s1 h)) (fst (exec_block b2 s2 h)))).
    - (* call *)
      intros G x y m ps1 ps2 Hps Hx Hy s1 s2 h Hrel. simpl.
      assert (Hq : eval_pieces s1 ps1 = eval_pieces s2 ps2).
      { rewrite <- (merge_eval s1 ps1), <- (merge_eval s2 ps2).
        now apply (pieces_equiv_eval G). }
      rewrite Hq. destruct (Pi m (eval_pieces s2 ps2) (tape (key_call h m (eval_pieces s2 ps2))))
        as [resp o]. simpl. split; [reflexivity |].
      intros u w Hin. unfold update. destruct Hin as [Heq | Hin].
      + inversion Heq; subst. now rewrite !String.eqb_refl.
      + destruct (String.eqb_spec x u) as [-> | _].
        { exfalso. apply Hx. apply (in_map fst) in Hin. exact Hin. }
        destruct (String.eqb_spec y w) as [-> | _].
        { exfalso. apply Hy. apply (in_map snd) in Hin. exact Hin. }
        now apply Hrel.
    - (* if *)
      intros G g1 g2 b1 b2 d1 d2 G1 G2 Hp Hin Hb1 IH1 Hb2 IH2 s1 s2 h Hrel. simpl.
      assert (Hg : eval_guard s1 g1 = eval_guard s2 g2).
      { unfold eval_guard. rewrite Hp. f_equal. now apply Hrel. }
      rewrite Hg. destruct (eval_guard s2 g2).
      + destruct (IH1 s1 s2 h Hrel) as [Hh Hr]. split; [assumption |].
        destruct (proj2 equiv_extends _ _ _ _ Hb1) as [E ->]. eapply related_weaken; eassumption.
      + destruct (IH2 s1 s2 h Hrel) as [Hh Hr]. split; [assumption |].
        destruct (proj2 equiv_extends _ _ _ _ Hb2) as [E ->]. eapply related_weaken; eassumption.
    - (* retry *)
      intros G n b d G' Hb IH s1 s2 h Hrel. simpl.
      apply (retry_loop_agree G). 2: assumption.
      intros a1 a2 h' Hr. destruct (IH a1 a2 h' Hr) as [Hh Hr']. split; [assumption |].
      destruct (proj2 equiv_extends _ _ _ _ Hb) as [E ->]. eapply related_weaken; eassumption.
    - (* nil *)
      intros G s1 s2 h Hrel. simpl. split; [reflexivity | assumption].
    - (* nop left *)
      intros G b d G' Hb IH s1 s2 h Hrel. simpl. now apply IH.
    - (* nop right *)
      intros G b d G' Hb IH s1 s2 h Hrel. simpl. now apply IH.
    - (* cons *)
      intros G G1 G2 st1 st2 b d Hs IHs Hb IHb s1 s2 h Hrel. simpl.
      destruct (IHs s1 s2 h Hrel) as [Hh Hr].
      destruct (exec_stmt st1 s1 h) as [a1 h1]. destruct (exec_stmt st2 s2 h) as [a2 h2].
      simpl in *. subst h2. now apply IHb.
  Qed.

  (* -------------------------------------------------------- resolution *)

  (* Which variables hold secrets.  A secret guard reads one. *)
  Variable secret : var -> bool.

  Definition secret_guard (g : guard) : bool := secret (gvar g).

  (* Resolve every secret guard by the outcome vector v, inlining the arm it
     selects.  Public guards are kept. *)
  Fixpoint resolve_stmt (v : guard -> bool) (st : stmt) : block :=
    match st with
    | SIf g b1 b2 =>
        if secret_guard g then (if v g then resolve_block v b1 else resolve_block v b2)
        else BCons (SIf g (resolve_block v b1) (resolve_block v b2)) BNil
    | SRetry n b => BCons (SRetry n (resolve_block v b)) BNil
    | other => BCons other BNil
    end
  with resolve_block (v : guard -> bool) (b : block) : block :=
    match b with
    | BNil => BNil
    | BCons st rest => app_block (resolve_stmt v st) (resolve_block v rest)
    end.

  (* No statement assigns a secret variable. *)
  Fixpoint no_secret_assign_stmt (st : stmt) : Prop :=
    match st with
    | SNop => True
    | SCall x _ _ => secret x = false
    | SIf _ b1 b2 => no_secret_assign_block b1 /\ no_secret_assign_block b2
    | SRetry _ b => no_secret_assign_block b
    end
  with no_secret_assign_block (b : block) : Prop :=
    match b with
    | BNil => True
    | BCons st rest => no_secret_assign_stmt st /\ no_secret_assign_block rest
    end.

  (* v gives the outcomes the store s gives, on every secret guard. *)
  Definition agrees (v : guard -> bool) (s : store) : Prop :=
    forall g, secret_guard g = true -> v g = eval_guard s g.

  Lemma retry_loop_invariant : forall (P : store -> Prop) body n s h,
      (forall s h, P s -> P (fst (body s h))) -> P s -> P (fst (retry_loop body n s h)).
  Proof.
    intros P body n. induction n as [| n IH]; intros s h Hbody Hs; simpl; [assumption |].
    pose proof (Hbody s h Hs) as H1. destruct (body s h) as [s1 h1]. simpl in H1.
    destruct (V _ _); simpl; [assumption | now apply IH].
  Qed.

  (* Executing code that assigns no secret leaves every secret as it was. *)
  Lemma secrets_preserved :
    (forall st s h, no_secret_assign_stmt st ->
       forall x, secret x = true -> fst (exec_stmt st s h) x = s x) /\
    (forall b s h, no_secret_assign_block b ->
       forall x, secret x = true -> fst (exec_block b s h) x = s x).
  Proof.
    apply (syntax_mut
      (fun st => forall s h, no_secret_assign_stmt st ->
         forall x, secret x = true -> fst (exec_stmt st s h) x = s x)
      (fun b => forall s h, no_secret_assign_block b ->
         forall x, secret x = true -> fst (exec_block b s h) x = s x)).
    - intros s h _ x _. reflexivity.
    - intros y m ps s h Hy x Hx. simpl.
      destruct (Pi m _ _) as [resp o]. simpl. unfold update.
      destruct (String.eqb_spec y x) as [-> | _]; [congruence | reflexivity].
    - intros g b1 IH1 b2 IH2 s h [H1 H2] x Hx. simpl.
      destruct (eval_guard s g); [now apply IH1 | now apply IH2].
    - intros n b IH s h Hb x Hx. simpl.
      apply (retry_loop_invariant (fun a => a x = s x)).
      + intros a h' Ha. rewrite <- Ha. now apply IH.
      + reflexivity.
    - intros s h _ x _. reflexivity.
    - intros st IHs rest IHr s h [Hs Hr] x Hx. simpl.
      specialize (IHs s h Hs x Hx). destruct (exec_stmt st s h) as [s1 h1]. simpl in IHs.
      rewrite <- IHs. now apply IHr.
  Qed.

  Lemma agrees_preserved : forall v s s',
      agrees v s -> (forall x, secret x = true -> s' x = s x) -> agrees v s'.
  Proof.
    intros v s s' Hag Hsec g Hg. rewrite (Hag g Hg). unfold eval_guard.
    unfold secret_guard in Hg. now rewrite (Hsec _ Hg).
  Qed.

  Lemma retry_loop_ext : forall body1 body2 (P : store -> Prop) n s h,
      (forall s h, P s -> body1 s h = body2 s h) ->
      (forall s h, P s -> P (fst (body1 s h))) ->
      P s -> retry_loop body1 n s h = retry_loop body2 n s h.
  Proof.
    intros body1 body2 P n. induction n as [| n IH]; intros s h Heq Hinv Hs; simpl; [reflexivity |].
    rewrite <- (Heq s h Hs). pose proof (Hinv s h Hs) as H1.
    destruct (body1 s h) as [s1 h1]. simpl in H1.
    destruct (V _ _); [reflexivity | now apply IH].
  Qed.

  (* Resolving by the outcomes the store actually gives changes nothing. *)
  Theorem resolve_exact :
    (forall st v s h, no_secret_assign_stmt st -> agrees v s ->
       exec_block (resolve_stmt v st) s h = exec_stmt st s h) /\
    (forall b v s h, no_secret_assign_block b -> agrees v s ->
       exec_block (resolve_block v b) s h = exec_block b s h).
  Proof.
    apply (syntax_mut
      (fun st => forall v s h, no_secret_assign_stmt st -> agrees v s ->
         exec_block (resolve_stmt v st) s h = exec_stmt st s h)
      (fun b => forall v s h, no_secret_assign_block b -> agrees v s ->
         exec_block (resolve_block v b) s h = exec_block b s h)).
    - intros v s h _ _. simpl. reflexivity.
    - intros x m ps v s h _ _. simpl.
      destruct (Pi m _ _) as [resp o]. reflexivity.
    - intros g b1 IH1 b2 IH2 v s h [H1 H2] Hag. simpl.
      destruct (secret_guard g) eqn:Hsg.
      + rewrite (Hag g Hsg). destruct (eval_guard s g); [now apply IH1 | now apply IH2].
      + simpl. destruct (eval_guard s g).
        * rewrite (IH1 v s h H1 Hag). now destruct (exec_block b1 s h).
        * rewrite (IH2 v s h H2 Hag). now destruct (exec_block b2 s h).
    - intros n b IH v s h Hb Hag. simpl.
      destruct (retry_loop (exec_block (resolve_block v b)) n s h) as [s' h'] eqn:E.
      rewrite <- E. symmetry.
      apply (retry_loop_ext _ _ (agrees v)).
      + intros a h'' Ha. symmetry. now apply IH.
      + intros a h'' Ha. apply (agrees_preserved v a).
        * assumption.
        * intros x Hx. now apply (proj2 secrets_preserved).
      + assumption.
    - intros v s h _ _. reflexivity.
    - intros st IHs rest IHr v s h [Hs Hr] Hag. simpl. rewrite exec_app.
      rewrite (IHs v s h Hs Hag).
      pose proof (proj1 secrets_preserved st s h Hs) as Hsec.
      destruct (exec_stmt st s h) as [s1 h1] eqn:E. simpl in Hsec.
      apply IHr; [assumption |].
      apply (agrees_preserved v s); [assumption |]. intros x Hx. now apply Hsec.
  Qed.

  (* ------------------------------------------------------ Theorem 1 *)

  Definition diag (xs : list var) : rel := map (fun x => (x, x)) xs.

  Lemma related_diag : forall xs s1 s2,
      (forall x, In x xs -> s1 x = s2 x) -> related (diag xs) s1 s2.
  Proof.
    intros xs s1 s2 H x y Hin. unfold diag in Hin. apply in_map_iff in Hin.
    destruct Hin as [z [Heq Hz]]. inversion Heq; subst. now apply H.
  Qed.

  (* Request-trace noninterference.  If a program's resolutions under the
     outcome vectors of two stores are related by the judgment, starting from
     the public variables on which the stores agree, the two executions produce
     the same history on every tape.  With k(c) = 1 every pair of feasible
     vectors is related, which is Theorem 1; in general the executions of
     stores whose vectors fall in one class coincide, which is the
     factorisation Theorem 2 rests on. *)
  Theorem request_trace_noninterference :
    forall (b : block) (pubs : list var) (s1 s2 : store) (v1 v2 : guard -> bool) G',
      (forall x, In x pubs -> s1 x = s2 x) ->
      agrees v1 s1 -> agrees v2 s2 ->
      no_secret_assign_block b ->
      bequiv (diag pubs) (resolve_block v1 b) (resolve_block v2 b) G' ->
      forall h, snd (exec_block b s1 h) = snd (exec_block b s2 h).
  Proof.
    intros b pubs s1 s2 v1 v2 G' Hpub Hag1 Hag2 Hns Heq h.
    rewrite <- (proj2 resolve_exact b v1 s1 h Hns Hag1).
    rewrite <- (proj2 resolve_exact b v2 s2 h Hns Hag2).
    apply (proj1 (proj2 equiv_sound _ _ _ _ Heq s1 s2 h (related_diag pubs s1 s2 Hpub))).
  Qed.

  (* Every observer of the history -- a log, an itemised bill under any
     tokenizer and prices, a total -- sees the same thing. *)
  Corollary observers_agree :
    forall (Obs : Type) (O : history -> Obs) b pubs s1 s2 v1 v2 G',
      (forall x, In x pubs -> s1 x = s2 x) ->
      agrees v1 s1 -> agrees v2 s2 ->
      no_secret_assign_block b ->
      bequiv (diag pubs) (resolve_block v1 b) (resolve_block v2 b) G' ->
      forall h, O (snd (exec_block b s1 h)) = O (snd (exec_block b s2 h)).
  Proof.
    intros. f_equal. eapply request_trace_noninterference; eassumption.
  Qed.

  (* ------------------------------------------- Theorem 5: the unary bound *)

  (* What the certificate's guaranteed bound assumes, as hypotheses:
       - the provider reports at most cap m output tokens;
       - a response is at most rbytes m bytes, which the implementation
         takes to be lambda * cap m for the model's tokenizer, or the client
         byte cap (docs/FORMAL_MODEL.md section 7 justifies this for lossless
         and U+FFFD-replacing decoding; here it is assumed);
       - billed input -- tokenizer plus envelope -- satisfies the tokenizer
         contract plus the declared overhead;
       - every variable's value is within a declared byte bound vb. *)
  Variable cap rbytes kappa sigma overhead : model -> nat.
  Variable bin : model -> string -> nat.
  Variable vb : var -> nat.

  Hypothesis Pi_cap : forall m q d, snd (Pi m q d) <= cap m.
  Hypothesis Pi_bytes : forall m q d, String.length (fst (Pi m q d)) <= rbytes m.
  Hypothesis bin_contract : forall m q,
      bin m q <= kappa m * String.length q + sigma m + overhead m.

  Fixpoint out_total (h : history) : nat :=
    match h with
    | [] => 0
    | EvCall _ _ _ o :: rest => o + out_total rest
    | EvAttempt _ :: rest => out_total rest
    end.

  Fixpoint in_total (h : history) : nat :=
    match h with
    | [] => 0
    | EvCall m q _ _ :: rest => bin m q + in_total rest
    | EvAttempt _ :: rest => in_total rest
    end.

  Lemma out_total_app : forall h1 h2, out_total (h1 ++ h2) = out_total h1 + out_total h2.
  Proof. induction h1 as [| [] rest IH]; intros; simpl; try rewrite IH; lia. Qed.

  Lemma in_total_app : forall h1 h2, in_total (h1 ++ h2) = in_total h1 + in_total h2.
  Proof. induction h1 as [| [] rest IH]; intros; simpl; try rewrite IH; lia. Qed.

  Definition bounded (s : store) : Prop := forall x, String.length (s x) <= vb x.

  Definition piece_bytes (p : piece) : nat :=
    match p with
    | PText t => String.length t
    | PLit t => String.length t
    | PVar x => vb x
    end.

  Fixpoint pieces_bytes (ps : list piece) : nat :=
    match ps with
    | [] => 0
    | p :: rest => piece_bytes p + pieces_bytes rest
    end.

  (* Bytes add up under concatenation; that is the whole reason the bound is
     computed in bytes. *)
  Lemma eval_pieces_bytes : forall s ps,
      bounded s -> String.length (eval_pieces s ps) <= pieces_bytes ps.
  Proof.
    intros s ps Hb. induction ps as [| p rest IH]; simpl; [lia |].
    rewrite sapp_length. destruct p as [t | t | x]; simpl; specialize (Hb); try lia.
    pose proof (Hb x). lia.
  Qed.

  (* The analysis: sum for sequencing, maximum for a branch, n times the body
     for a retry. *)
  Fixpoint ob_stmt (st : stmt) : nat :=
    match st with
    | SNop => 0
    | SCall _ m _ => cap m
    | SIf _ b1 b2 => Nat.max (ob_block b1) (ob_block b2)
    | SRetry n b => n * ob_block b
    end
  with ob_block (b : block) : nat :=
    match b with
    | BNil => 0
    | BCons st rest => ob_stmt st + ob_block rest
    end.

  Fixpoint ib_stmt (st : stmt) : nat :=
    match st with
    | SNop => 0
    | SCall _ m ps => kappa m * pieces_bytes ps + sigma m + overhead m
    | SIf _ b1 b2 => Nat.max (ib_block b1) (ib_block b2)
    | SRetry n b => n * ib_block b
    end
  with ib_block (b : block) : nat :=
    match b with
    | BNil => 0
    | BCons st rest => ib_stmt st + ib_block rest
    end.

  (* Every binding's declared byte bound covers the responses it can receive. *)
  Fixpoint wf_stmt (st : stmt) : Prop :=
    match st with
    | SNop => True
    | SCall x m _ => rbytes m <= vb x
    | SIf _ b1 b2 => wf_block b1 /\ wf_block b2
    | SRetry _ b => wf_block b
    end
  with wf_block (b : block) : Prop :=
    match b with
    | BNil => True
    | BCons st rest => wf_stmt st /\ wf_block rest
    end.

  Definition within (run : store * history) (s : store) (h : history) (ob ib : nat) : Prop :=
    exists t, snd run = h ++ t /\ out_total t <= ob /\ in_total t <= ib /\ bounded (fst run).

  Lemma retry_loop_bound : forall body n ob ib,
      (forall s h, bounded s -> within (body s h) s h ob ib) ->
      forall s h, bounded s -> within (retry_loop body n s h) s h (n * ob) (n * ib).
  Proof.
    intros body n ob ib Hbody. induction n as [| n IH]; intros s h Hs; simpl.
    - exists []. rewrite app_nil_r. simpl. repeat split; try lia. assumption.
    - destruct (Hbody s h Hs) as [t1 [Ht1 [Ho1 [Hi1 Hs1]]]].
      destruct (body s h) as [s1 h1]. simpl in *. subst h1.
      rewrite skipn_app, Nat.sub_diag, skipn_all. simpl.
      destruct (V t1 _).
      + exists (t1 ++ [EvAttempt true]). rewrite app_assoc.
        rewrite out_total_app, in_total_app. simpl. repeat split; try lia. assumption.
      + destruct (IH s1 ((h ++ t1) ++ [EvAttempt false]) Hs1) as [t2 [Ht2 [Ho2 [Hi2 Hs2]]]].
        exists (t1 ++ EvAttempt false :: t2). split.
        * rewrite Ht2. rewrite <- !app_assoc. reflexivity.
        * rewrite out_total_app, in_total_app. simpl. repeat split; try lia. assumption.
  Qed.

  Theorem unary_bound :
    (forall st s h, wf_stmt st -> bounded s -> within (exec_stmt st s h) s h (ob_stmt st) (ib_stmt st)) /\
    (forall b s h, wf_block b -> bounded s -> within (exec_block b s h) s h (ob_block b) (ib_block b)).
  Proof.
    apply (syntax_mut
      (fun st => forall s h, wf_stmt st -> bounded s ->
         within (exec_stmt st s h) s h (ob_stmt st) (ib_stmt st))
      (fun b => forall s h, wf_block b -> bounded s ->
         within (exec_block b s h) s h (ob_block b) (ib_block b))).
    - intros s h _ Hs. exists []. rewrite app_nil_r. simpl. repeat split; try lia. assumption.
    - intros x m ps s h Hwf Hs. simpl in Hwf |- *.
      pose proof (Pi_cap m (eval_pieces s ps) (tape (key_call h m (eval_pieces s ps)))) as Hc.
      pose proof (Pi_bytes m (eval_pieces s ps) (tape (key_call h m (eval_pieces s ps)))) as Hy.
      destruct (Pi m _ _) as [resp o]. simpl in Hc, Hy.
      exists [EvCall m (eval_pieces s ps) resp o]. simpl. split; [reflexivity |].
      pose proof (bin_contract m (eval_pieces s ps)) as Hk.
      pose proof (eval_pieces_bytes s ps Hs) as Hq.
      repeat split.
      + lia.
      + pose proof (Nat.mul_le_mono_l _ _ (kappa m) Hq). lia.
      + intros y. unfold update. destruct (String.eqb_spec x y) as [<- | _]; [lia | apply Hs].
    - intros g b1 IH1 b2 IH2 s h [H1 H2] Hs. simpl.
      destruct (eval_guard s g).
      + destruct (IH1 s h H1 Hs) as [t [Ht [Ho [Hi Hb]]]].
        exists t. repeat split; try assumption; lia.
      + destruct (IH2 s h H2 Hs) as [t [Ht [Ho [Hi Hb]]]].
        exists t. repeat split; try assumption; lia.
    - intros n b IH s h Hb Hs. simpl.
      apply retry_loop_bound; [| assumption].
      intros a h' Ha. now apply IH.
    - intros s h _ Hs. exists []. rewrite app_nil_r. simpl. repeat split; try lia. assumption.
    - intros st IHs rest IHr s h [Hw Hr] Hs. simpl.
      destruct (IHs s h Hw Hs) as [t1 [Ht1 [Ho1 [Hi1 Hs1]]]].
      destruct (exec_stmt st s h) as [s1 h1]. simpl in *. subst h1.
      destruct (IHr s1 (h ++ t1) Hr Hs1) as [t2 [Ht2 [Ho2 [Hi2 Hs2]]]].
      exists (t1 ++ t2). split.
      + rewrite Ht2. now rewrite app_assoc.
      + rewrite out_total_app, in_total_app. repeat split; try lia. assumption.
  Qed.

  (* The certificate's figures, from the empty history. *)
  Corollary guaranteed_bound : forall b s,
      wf_block b -> bounded s ->
      out_total (snd (exec_block b s [])) <= ob_block b /\
      in_total (snd (exec_block b s [])) <= ib_block b /\
      out_total (snd (exec_block b s [])) + in_total (snd (exec_block b s []))
        <= ob_block b + ib_block b.
  Proof.
    intros b s Hw Hs. destruct (proj2 unary_bound b s [] Hw Hs) as [t [Ht [Ho [Hi _]]]].
    rewrite Ht. simpl. repeat split; lia.
  Qed.

End Semantics.


(* ------------------------------------------ Theorem 6: size-blindness *)

(* An analysis is a predicate on programs ("accepted").  It is mu-indexed if
   it cannot tell apart two programs of the same shape whose text constants
   have equal size under mu.  It is sound (in the weakest sense used here) if
   every accepted program gives the same total output-token count from any two
   stores that agree on the public variables, for every deterministic provider
   that respects the output caps.  Total output tokens are a function of the
   bill, so any analysis sound for the bill, the provider or the trace
   observer is sound in this sense; and a deterministic provider is a
   provider.

   Theorem 6: a sound mu-indexed analysis rejects every program that has a
   secret-guarded branch, with both outcomes realisable, whose then-arm makes
   a call to a model with a positive cap whose request contains a text
   constant with a "fresh twin" -- a string of the same size containing a
   character that no text constant of the program contains.  The arms may be
   identical. *)

Section SizeBlindness.

  Variable interp : nat -> string -> bool.
  Variable secret : var -> bool.
  Variable mu : string -> nat.
  Variable cap : model -> nat.

  Inductive psize : piece -> piece -> Prop :=
  | PSText : forall a b, mu a = mu b -> psize (PText a) (PText b)
  | PSLit : forall a b, mu a = mu b -> psize (PLit a) (PLit b)
  | PSVar : forall x, psize (PVar x) (PVar x).

  Inductive ssize : stmt -> stmt -> Prop :=
  | SSNop : ssize SNop SNop
  | SSCall : forall x m ps ps', Forall2 psize ps ps' -> ssize (SCall x m ps) (SCall x m ps')
  | SSIf : forall g b1 b2 d1 d2, bsize b1 d1 -> bsize b2 d2 -> ssize (SIf g b1 b2) (SIf g d1 d2)
  | SSRetry : forall n b d, bsize b d -> ssize (SRetry n b) (SRetry n d)
  with bsize : block -> block -> Prop :=
  | BSNil : bsize BNil BNil
  | BSCons : forall s d b e, ssize s d -> bsize b e -> bsize (BCons s b) (BCons d e).

  Definition mu_indexed (A : block -> Prop) : Prop :=
    forall b b', bsize b b' -> A b -> A b'.

  (* The deterministic instance of the semantics. *)
  Definition drun (P : model -> string -> string * nat) (Vd : history -> bool)
             (b : block) (s : store) : store * history :=
    exec_block unit unit interp (fun _ _ _ => tt) (fun _ _ => tt) (fun _ => tt)
               (fun m q _ => P m q) (fun h _ => Vd h) b s [].

  Definition sound_for_total (A : block -> Prop) : Prop :=
    forall b, A b ->
    forall P Vd s1 s2,
      (forall m q, snd (P m q) <= cap m) ->
      (forall x, secret x = false -> s1 x = s2 x) ->
      out_total (snd (drun P Vd b s1)) = out_total (snd (drun P Vd b s2)).

  Lemma psize_refl : forall p, psize p p.
  Proof. destruct p; constructor; reflexivity. Qed.

  Lemma bsize_refl : (forall st, ssize st st) /\ (forall b, bsize b b).
  Proof.
    apply (syntax_mut (fun st => ssize st st) (fun b => bsize b b)); intros; try constructor; auto.
    induction l; constructor; auto using psize_refl.
  Qed.

  Lemma bsize_app : forall a a' b b', bsize a a' -> bsize b b' ->
      bsize (app_block a b) (app_block a' b').
  Proof. intros a a' b b' Ha Hb. induction Ha; simpl; [assumption | constructor; auto]. Qed.

  (* ------------------------------------------------ the fresh character *)

  Variable ch : ascii.

  Fixpoint has_char (u : string) : bool :=
    match u with
    | EmptyString => false
    | String a rest => Ascii.eqb a ch || has_char rest
    end.

  Lemma has_char_app : forall a b, has_char (sapp a b) = has_char a || has_char b.
  Proof. induction a; intros; simpl; [reflexivity | now rewrite IHa, orb_assoc]. Qed.

  (* No text constant contains ch, and no request reads a secret (E230). *)
  Definition piece_ok (p : piece) : bool :=
    match p with
    | PText t => negb (has_char t)
    | PLit t => negb (has_char t)
    | PVar x => negb (secret x)
    end.

  Fixpoint ok_stmt (st : stmt) : Prop :=
    match st with
    | SNop => True
    | SCall _ _ ps => forallb piece_ok ps = true
    | SIf _ b1 b2 => ok_block b1 /\ ok_block b2
    | SRetry _ b => ok_block b
    end
  with ok_block (b : block) : Prop :=
    match b with
    | BNil => True
    | BCons st rest => ok_stmt st /\ ok_block rest
    end.

  Lemma ok_app : forall a b, ok_block (app_block a b) <-> ok_block a /\ ok_block b.
  Proof. induction a; intros; simpl; [tauto | rewrite IHa; tauto]. Qed.

  Definition clean (s : store) : Prop := forall x, secret x = false -> has_char (s x) = false.

  Lemma clean_request : forall s ps,
      clean s -> forallb piece_ok ps = true -> has_char (eval_pieces s ps) = false.
  Proof.
    intros s ps Hs. induction ps as [| p rest IH]; simpl; [reflexivity |].
    intros H. apply andb_prop in H as [Hp Hr]. rewrite has_char_app, IH by assumption.
    destruct p as [t | t | x]; simpl in *; try (now destruct (has_char t)).
    rewrite Hs; [reflexivity |]. now destruct (secret x).
  Qed.

  Lemma marked_request : forall s ps t,
      In (PText t) ps -> has_char t = true -> has_char (eval_pieces s ps) = true.
  Proof.
    intros s ps t. induction ps as [| p rest IH]; simpl; [tauto |].
    intros [-> | Hin] Ht; rewrite has_char_app.
    - simpl. now rewrite Ht.
    - rewrite IH by assumption. apply orb_true_r.
  Qed.

  (* The provider of the proof: an empty response, and the full cap exactly
     when the request contains ch.  The validator always accepts. *)
  Definition Pstar (m : model) (q : string) : string * nat :=
    (""%string, if has_char q then cap m else 0).
  Definition Vstar (_ : history) : bool := true.

  Definition xstmt := exec_stmt unit unit interp (fun _ _ _ => tt) (fun _ _ => tt) (fun _ => tt)
                                (fun m q _ => Pstar m q) (fun h _ => Vstar h).
  Definition xblock := exec_block unit unit interp (fun _ _ _ => tt) (fun _ _ => tt) (fun _ => tt)
                                  (fun m q _ => Pstar m q) (fun h _ => Vstar h).

  Definition xretry := retry_loop unit unit (fun _ _ => tt) (fun _ => tt) (fun h _ => Vstar h).

  Lemma x_nop : forall s h, xstmt SNop s h = (s, h).
  Proof. reflexivity. Qed.
  Lemma x_call : forall x m ps s h,
      xstmt (SCall x m ps) s h =
      (update s x ""%string,
       h ++ [EvCall m (eval_pieces s ps) ""%string
               (if has_char (eval_pieces s ps) then cap m else 0)]).
  Proof. reflexivity. Qed.
  Lemma x_if : forall g b1 b2 s h,
      xstmt (SIf g b1 b2) s h = if eval_guard interp s g then xblock b1 s h else xblock b2 s h.
  Proof. reflexivity. Qed.
  Lemma x_retry : forall n b s h, xstmt (SRetry n b) s h = xretry (xblock b) n s h.
  Proof. reflexivity. Qed.
  Lemma x_nil : forall s h, xblock BNil s h = (s, h).
  Proof. reflexivity. Qed.
  Lemma x_cons : forall st rest s h,
      xblock (BCons st rest) s h = let '(s1, h1) := xstmt st s h in xblock rest s1 h1.
  Proof. reflexivity. Qed.
  Lemma x_app : forall b1 b2 s h,
      xblock (app_block b1 b2) s h = let '(s1, h1) := xblock b1 s h in xblock b2 s1 h1.
  Proof. intros. apply exec_app. Qed.

  (* Code whose text avoids ch, from a clean store, reports no output. *)
  Lemma silent :
    (forall st s h, ok_stmt st -> clean s ->
       exists t, snd (xstmt st s h) = h ++ t /\ out_total t = 0 /\ clean (fst (xstmt st s h))) /\
    (forall b s h, ok_block b -> clean s ->
       exists t, snd (xblock b s h) = h ++ t /\ out_total t = 0 /\ clean (fst (xblock b s h))).
  Proof.
    apply (syntax_mut
      (fun st => forall s h, ok_stmt st -> clean s ->
         exists t, snd (xstmt st s h) = h ++ t /\ out_total t = 0 /\ clean (fst (xstmt st s h)))
      (fun b => forall s h, ok_block b -> clean s ->
         exists t, snd (xblock b s h) = h ++ t /\ out_total t = 0 /\ clean (fst (xblock b s h)))).
    - intros s h _ Hs. rewrite x_nop. exists []. rewrite app_nil_r. auto.
    - intros x m ps s h Hok Hs. simpl in Hok. rewrite x_call.
      rewrite (clean_request s ps Hs Hok). simpl.
      eexists. split; [reflexivity |]. split; [reflexivity |].
      intros y Hy. unfold update. destruct (String.eqb x y); [reflexivity | now apply Hs].
    - intros g b1 IH1 b2 IH2 s h [H1 H2] Hs. rewrite x_if.
      destruct (eval_guard interp s g); auto.
    - intros n b IH s h Hb Hs. rewrite x_retry. unfold xretry.
      apply (retry_loop_extends unit unit _ _ _ clean (fun t => out_total t = 0)).
      + reflexivity.
      + reflexivity.
      + intros t1 t2 H1 H2. rewrite out_total_app. lia.
      + intros a h' Ha. now apply IH.
      + assumption.
    - intros s h _ Hs. rewrite x_nil. exists []. rewrite app_nil_r. auto.
    - intros st IHs rest IHr s h [Hs Hr] Hc. rewrite x_cons.
      destruct (IHs s h Hs Hc) as [t1 [Ht1 [Ho1 Hc1]]].
      destruct (xstmt st s h) as [s1 h1]. simpl in *. subst h1.
      destruct (IHr s1 (h ++ t1) Hr Hc1) as [t2 [Ht2 [Ho2 Hc2]]].
      exists (t1 ++ t2). rewrite Ht2, app_assoc, out_total_app. repeat split; auto; lia.
  Qed.

  Lemma xblock_extends : forall b s h, exists t, snd (xblock b s h) = h ++ t.
  Proof. intros. apply exec_extends. Qed.

  Lemma out_mono_block : forall b s h, out_total h <= out_total (snd (xblock b s h)).
  Proof.
    intros b s h. destruct (xblock_extends b s h) as [t ->]. rewrite out_total_app. lia.
  Qed.

  Lemma guard_kept : forall pre g s h,
      no_secret_assign_block secret pre -> secret (gvar g) = true ->
      eval_guard interp (fst (xblock pre s h)) g = eval_guard interp s g.
  Proof.
    intros pre g s h Hpre Hsec. unfold eval_guard. f_equal.
    apply (proj2 (secrets_preserved unit unit interp (fun _ _ _ => tt) (fun _ _ => tt) (fun _ => tt)
                    (fun m q _ => Pstar m q) (fun h _ => Vstar h) secret)); assumption.
  Qed.

  (* The execution that takes the then-arm reports at least cap m. *)
  Lemma run_then : forall pre g pre1 x m ps b1 b2 post s t,
      ok_block pre -> ok_block pre1 -> clean s ->
      no_secret_assign_block secret pre -> secret (gvar g) = true ->
      eval_guard interp s g = true -> In (PText t) ps -> has_char t = true ->
      cap m <= out_total (snd (xblock
        (app_block pre (BCons (SIf g (app_block pre1 (BCons (SCall x m ps) b1)) b2) post)) s [])).
  Proof.
    intros pre g pre1 x m ps b1 b2 post s t Hpre Hpre1 Hs Hns Hsec Hg Hin Ht.
    pose proof (guard_kept pre g s [] Hns Hsec) as Hkeep.
    destruct (proj2 silent pre s [] Hpre Hs) as [p1 [Hp1 [_ Hc1]]].
    rewrite x_app. destruct (xblock pre s []) as [a1 k1]. simpl in Hp1, Hc1, Hkeep. subst k1.
    rewrite x_cons, x_if, Hkeep, Hg.
    destruct (xblock (app_block pre1 (BCons (SCall x m ps) b1)) a1 p1) as [a2 k2] eqn:E.
    eapply Nat.le_trans; [| apply out_mono_block]. simpl.
    rewrite x_app in E.
    destruct (proj2 silent pre1 a1 p1 Hpre1 Hc1) as [p2 [Hp2 [_ Hc2]]].
    destruct (xblock pre1 a1 p1) as [a3 k3]. simpl in Hp2, Hc2. subst k3.
    rewrite x_cons, x_call in E.
    rewrite (marked_request a3 ps t Hin Ht) in E.
    pose proof (out_mono_block b1 (update a3 x ""%string)
                  ((p1 ++ p2) ++ [EvCall m (eval_pieces a3 ps) ""%string (cap m)])) as Hm.
    rewrite E in Hm. simpl in Hm.
    rewrite !out_total_app in Hm. simpl in Hm. lia.
  Qed.

  (* The execution that takes the else-arm reports nothing. *)
  Lemma run_else : forall pre g th b2 post s,
      ok_block pre -> ok_block b2 -> ok_block post -> clean s ->
      no_secret_assign_block secret pre -> secret (gvar g) = true ->
      eval_guard interp s g = false ->
      out_total (snd (xblock (app_block pre (BCons (SIf g th b2) post)) s [])) = 0.
  Proof.
    intros pre g th b2 post s Hpre Hb2 Hpost Hs Hns Hsec Hg.
    pose proof (guard_kept pre g s [] Hns Hsec) as Hkeep.
    destruct (proj2 silent pre s [] Hpre Hs) as [p1 [Hp1 [Ho1 Hc1]]].
    rewrite x_app. destruct (xblock pre s []) as [a1 k1]. simpl in Hp1, Hc1, Hkeep. subst k1.
    rewrite x_cons, x_if, Hkeep, Hg.
    destruct (proj2 silent b2 a1 p1 Hb2 Hc1) as [p2 [Hp2 [Ho2 Hc2]]].
    destruct (xblock b2 a1 p1) as [a2 k2]. simpl in Hp2, Hc2. subst k2.
    destruct (proj2 silent post a2 (p1 ++ p2) Hpost Hc2) as [p3 [Hp3 [Ho3 _]]].
    rewrite Hp3. rewrite !out_total_app. simpl. lia.
  Qed.

  Definition mark (t t' : string) (p : piece) : piece :=
    match p with
    | PText u => if String.eqb u t then PText t' else p
    | _ => p
    end.

  Lemma mark_size : forall t t' ps, mu t' = mu t -> Forall2 psize ps (map (mark t t') ps).
  Proof.
    intros t t' ps Hmu. induction ps as [| p rest IH]; simpl; constructor; auto.
    destruct p as [u | u | y]; simpl; try apply psize_refl.
    destruct (String.eqb_spec u t) as [-> | _]; constructor; auto.
  Qed.

  Lemma mark_in : forall t t' ps, In (PText t) ps -> In (PText t') (map (mark t t') ps).
  Proof.
    intros t t' ps Hin. apply in_map_iff. exists (PText t). split; [| assumption].
    simpl. now rewrite String.eqb_refl.
  Qed.

  Theorem size_blind :
    forall (A : block -> Prop) pre g pre1 x m ps b1 b2 post t t' u1 u2,
      mu_indexed A -> sound_for_total A ->
      (* the branch is on a secret, both outcomes are realisable, and the code
         before it does not overwrite secrets *)
      secret (gvar g) = true ->
      interp (gpred g) u1 = true -> interp (gpred g) u2 = false ->
      no_secret_assign_block secret pre ->
      (* the then-arm calls a model that can report output, with t in the request *)
      cap m > 0 -> In (PText t) ps ->
      (* t has a fresh twin t': same size, and a character no text constant of
         the program contains; no request reads a secret *)
      mu t' = mu t -> has_char t' = true ->
      ok_block (app_block pre (BCons (SIf g (app_block pre1 (BCons (SCall x m ps) b1)) b2) post)) ->
      ~ A (app_block pre (BCons (SIf g (app_block pre1 (BCons (SCall x m ps) b1)) b2) post)).
  Proof.
    intros A pre g pre1 x m ps b1 b2 post t t' u1 u2 Hidx Hsound
           Hsec Hu1 Hu2 Hns Hcap Hin Hmu Hfresh Hok HA.
    set (ps' := map (mark t t') ps).
    set (c' := app_block pre (BCons (SIf g (app_block pre1 (BCons (SCall x m ps') b1)) b2) post)).
    assert (HA' : A c').
    { eapply Hidx; [| exact HA]. unfold c'.
      apply bsize_app; [apply bsize_refl |].
      constructor; [| apply bsize_refl]. constructor; [| apply bsize_refl].
      apply bsize_app; [apply bsize_refl |].
      constructor; [| apply bsize_refl]. constructor. now apply mark_size. }
    set (s1 := fun y => if String.eqb y (gvar g) then u1 else ""%string).
    set (s2 := fun y => if String.eqb y (gvar g) then u2 else ""%string).
    assert (Hagree : forall y, secret y = false -> s1 y = s2 y).
    { intros y Hy. unfold s1, s2. destruct (String.eqb_spec y (gvar g)) as [-> | _]; congruence. }
    assert (Hc1 : clean s1).
    { intros y Hy. unfold s1. destruct (String.eqb_spec y (gvar g)) as [-> | _]; [congruence | reflexivity]. }
    assert (Hc2 : clean s2).
    { intros y Hy. unfold s2. destruct (String.eqb_spec y (gvar g)) as [-> | _]; [congruence | reflexivity]. }
    assert (Hcaps : forall m q, snd (Pstar m q) <= cap m).
    { intros. unfold Pstar. simpl. destruct (has_char q); lia. }
    assert (Hg1 : eval_guard interp s1 g = true).
    { unfold eval_guard, s1. now rewrite String.eqb_refl. }
    assert (Hg2 : eval_guard interp s2 g = false).
    { unfold eval_guard, s2. now rewrite String.eqb_refl. }
    pose proof (Hsound c' HA' Pstar Vstar s1 s2 Hcaps Hagree) as Heq.
    change (out_total (snd (xblock c' s1 [])) = out_total (snd (xblock c' s2 []))) in Heq.
    apply ok_app in Hok as [Hokpre Hrest]. simpl in Hrest.
    destruct Hrest as [[Hthen Hok2] Hokpost].
    apply ok_app in Hthen as [Hokpre1 _].
    pose proof (run_then pre g pre1 x m ps' b1 b2 post s1 t'
                  Hokpre Hokpre1 Hc1 Hns Hsec Hg1 (mark_in t t' ps Hin) Hfresh) as H1.
    pose proof (run_else pre g (app_block pre1 (BCons (SCall x m ps') b1)) b2 post s2
                  Hokpre Hok2 Hokpost Hc2 Hns Hsec Hg2) as H2.
    fold c' in H1, H2. lia.
  Qed.

End SizeBlindness.
