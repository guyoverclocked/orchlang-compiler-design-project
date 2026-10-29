import Utf8Envelope

/-! ### Noninterference, preservation and budgets on an admitted domain

`World.Conforms` and `World.Transparent` quantify over every request and target,
including targets smaller than the request. A non-truncating padder cannot meet
that obligation. This file restates the core results with the realistic
premises `ConformsOn D` and `TransparentOn D`, which constrain only requests in
`D`, together with `RunsIn`, which says every padded call and dummy reached by
an execution lies in `D`.

The static admission certificate discharges `RunsIn` for every bounded store
and every tape (`static_certificate_implies_RunsIn`). The certified theorems at
the end therefore need no global conformance, no global transparency and no
lookahead over future model responses: only the domain-restricted serving
contracts and the decidable checks performed by the validator and certificate.
Unlike `shape_exec_on`, the noninterference theorem here also covers programs
whose usage shape depends on public inputs.
-/

namespace OrchLang.Shape

/-- Visible-prefix transparency, required only for requests in `D`. -/
def World.TransparentOn (w : World) (D : RequestDomain) : Prop :=
  ∀ m k T N r c, k ≤ N → D m T N r →
    w.view m k (w.forced m (w.padReq m T r) c N) = w.gen m r k c

theorem World.Conforms.on (w : World) (hw : w.Conforms) (D : RequestDomain) :
    w.ConformsOn D :=
  fun m T N r _ => ⟨hw.1 m T r, fun c => hw.2 m _ c N⟩

theorem World.Transparent.on (w : World) (ht : w.Transparent) (D : RequestDomain) :
    w.TransparentOn D :=
  fun m k T N r c hk _ => ht m k T N r c hk

/-! #### Relational loop lemmas carrying the admission predicate -/

theorem loopRun_low_on (step ghostStep : St → St) (g : Guard) (padded : Bool)
    (R : St → St → Prop) (P : St → Prop) (cover : Prop)
    (hstep : ∀ a b, R a b → P a → P b → R (step a) (step b))
    (hghost : ∀ a b, R a b → R (ghostStep a) (ghostStep b))
    (hguard : ∀ a b, R a b → holds a.store g = holds b.store g) :
    ∀ n a b, R a b → loopIn step P cover g padded n a → loopIn step P cover g padded n b →
      R (loopRun step ghostStep g padded n a) (loopRun step ghostStep g padded n b) := by
  have hiter : ∀ m a b, R a b → R (iter ghostStep m a) (iter ghostStep m b) := by
    intro m
    induction m with
    | zero => intro a b h; exact h
    | succ m ih => intro a b h; exact ih _ _ (hghost a b h)
  intro n
  induction n with
  | zero => intro a b h _ _; simpa [loopRun] using h
  | succ n ih =>
      intro a b h ha hb
      have hg := hguard a b h
      by_cases hh : holds a.store g = true
      · have hb' : holds b.store g = true := by rw [← hg]; exact hh
        cases padded
        · simp [loopRun, hh, hb']; exact h
        · simp [loopRun, hh, hb']; exact hiter _ _ _ h
      · have hb' : ¬ holds b.store g = true := by rw [← hg]; exact hh
        simp [loopIn, hh] at ha
        simp [loopIn, hb'] at hb
        simp [loopRun, hh, hb']
        exact ih _ _ (hstep a b h ha.1 hb.1) ha.2 hb.2

theorem loopRun_rel2_on (s1 s2 g1 g2 : St → St) (g : Guard) (p1 p2 : Bool)
    (R : St → St → Prop) (P : St → Prop) (cover : Prop)
    (hs : ∀ a b, R a b → P a → R (s1 a) (s2 b))
    (hg1 : ∀ a b, R a b → R (g1 a) b) (hg2 : ∀ a b, R a b → R a (g2 b))
    (hguard : ∀ a b, R a b → holds a.store g = holds b.store g) :
    ∀ n a b, R a b → loopIn s1 P cover g p1 n a →
      R (loopRun s1 g1 g p1 n a) (loopRun s2 g2 g p2 n b) := by
  have i1 : ∀ m a b, R a b → R (iter g1 m a) b := by
    intro m; induction m with
    | zero => intro a b h; exact h
    | succ m ih => intro a b h; exact ih _ _ (hg1 a b h)
  have i2 : ∀ m a b, R a b → R a (iter g2 m b) := by
    intro m; induction m with
    | zero => intro a b h; exact h
    | succ m ih => intro a b h; exact ih _ _ (hg2 a b h)
  intro n
  induction n with
  | zero => intro a b h _; simpa [loopRun] using h
  | succ n ih =>
      intro a b h ha
      have hg := hguard a b h
      by_cases hh : holds a.store g = true
      · have hb : holds b.store g = true := by rw [← hg]; exact hh
        cases p1 <;> cases p2 <;> simp [loopRun, hh, hb] <;>
          first | exact h | exact i1 _ _ _ h | exact i2 _ _ _ h | exact i1 _ _ _ (i2 _ _ _ h)
      · have hb : ¬ holds b.store g = true := by rw [← hg]; exact hh
        simp [loopIn, hh] at ha
        simp [loopRun, hh, hb]
        exact ih _ _ (hs a b h ha.1) ha.2

/-! #### Theorem 3 on an admitted domain -/

theorem noninterference_on (w : World) (D : RequestDomain) (hw : w.ConformsOn D)
    (ω : Nat → Nat → Nat) (Γ : Ctx) (H : Nat → Bool) :
    ∀ (s : Stmt), wt Γ .low s = true → sitesOK Γ H .low s = true →
      ∀ a b, related Γ H a b → RunsIn w ω D s a → RunsIn w ω D s b →
        related Γ H (exec w ω s a) (exec w ω s b) := by
  intro s
  induction s with
  | skip => intro _ _ a b h _ _; exact h
  | seq x y ihx ihy =>
      intro hwt hs a b h ha hb
      simp [wt] at hwt; simp [sitesOK] at hs
      obtain ⟨hxa, hya⟩ := ha
      obtain ⟨hxb, hyb⟩ := hb
      exact ihy hwt.2 hs.2 _ _ (ihx hwt.1 hs.1 a b h hxa hxb) hya hyb
  | call i x m k e p =>
      intro hwt hs a b h ha hb
      obtain ⟨hl, hc, ht⟩ := h
      simp [sitesOK] at hs
      have hci : a.count i = b.count i := hc i (by simpa using hs)
      have hbump : agreeOff H (bump a.count i) (bump b.count i) := by
        intro j hj
        by_cases hji : j = i
        · subst hji; simp [bump, hci]
        · simp [bump, hji]; exact hc j hj
      cases hlab : labelE Γ e with
      | low =>
          have hr := evalE_low Γ _ _ hl e hlab
          cases p with
          | none =>
              refine ⟨?_, hbump, ?_⟩
              · intro z hz; simp [exec, upd]; split
                · rw [hr, hci]
                · exact hl z hz
              · simp [exec, ht, hr, hci]
          | some tn =>
              obtain ⟨T, N⟩ := tn
              refine ⟨?_, hbump, ?_⟩
              · intro z hz; simp [exec, upd]; split
                · rw [hr, hci]
                · exact hl z hz
              · simp [exec, ht, hr, hci]
      | high =>
          simp [wt, Label.join, hlab] at hwt
          have hx := le_high_right _ hwt.1
          cases p with
          | none => simp at hwt
          | some tn =>
              obtain ⟨T, N⟩ := tn
              have hca := hw m T N _ ha
              have hcb := hw m T N _ hb
              refine ⟨?_, hbump, ?_⟩
              · intro z hz
                have hne : z ≠ x := by intro hzx; subst hzx; rw [hz] at hx; cases hx
                simp [exec, upd, hne]; exact hl z hz
              · simp [exec, ht, hca.1, hca.2, hcb.1, hcb.2]
  | tool x t e =>
      intro hwt _ a b h _ _
      obtain ⟨hl, hc, ht⟩ := h
      refine ⟨?_, hc, ?_⟩
      · intro z hz
        simp [exec, upd]
        split
        · rename_i hzx; subst hzx
          cases hlab : labelE Γ e with
          | low => rw [evalE_low Γ _ _ hl e hlab]
          | high =>
              simp [wt, Label.join, hlab] at hwt
              have := le_high_right _ hwt; rw [hz] at this; cases this
        · exact hl z hz
      · simp [exec, ht]
  | dummy m T N =>
      intro _ _ a b h _ _
      obtain ⟨hl, hc, ht⟩ := h
      exact ⟨hl, hc, by simp [exec, ht]⟩
  | dummyTool t =>
      intro _ _ a b h _ _
      obtain ⟨hl, hc, ht⟩ := h
      exact ⟨hl, hc, by simp [exec, ht]⟩
  | ite g x y ihx ihy =>
      intro hwt hs a b h ha hb
      cases hgl : Γ (guardVar g) with
      | low =>
          simp [wt, sitesOK, Label.join, hgl] at hwt hs
          have hg := holds_low Γ _ _ h.1 g hgl
          by_cases hh : holds a.store g = true
          · have hb' : holds b.store g = true := by rw [← hg]; exact hh
            simp [RunsIn, hh] at ha; simp [RunsIn, hb'] at hb
            simp [exec, hh, hb']; exact ihx hwt.1 hs.1 a b h ha hb
          · have hb' : ¬ holds b.store g = true := by rw [← hg]; exact hh
            simp [RunsIn, hh] at ha; simp [RunsIn, hb'] at hb
            simp [exec, hh, hb']; exact ihy hwt.2 hs.2 a b h ha hb
      | high =>
          simp [wt, sitesOK, Label.join, hgl] at hwt hs
          obtain ⟨⟨hwx, hwy⟩, hsh⟩ := hwt
          obtain ⟨sh, hsheq⟩ := Option.isSome_iff_exists.mp hsh
          have hstore : ∀ st, lowEq Γ st.store (exec w ω (.ite g x y) st).store := by
            intro st z hz
            by_cases hh : holds st.store g = true
            · simp [exec, hh]; exact high_store w ω Γ x hwx st z hz
            · simp [exec, hh]; exact high_store w ω Γ y hwy st z hz
          have hcount : ∀ st j, H j = false → (exec w ω (.ite g x y) st).count j = st.count j := by
            intro st j hj
            by_cases hh : holds st.store g = true
            · simp [exec, hh]; exact high_count w ω Γ H x hs.1 st j hj
            · simp [exec, hh]; exact high_count w ω Γ H y hs.2 st j hj
          obtain ⟨hl, hc, ht⟩ := h
          refine ⟨?_, ?_, ?_⟩
          · intro z hz; rw [← hstore a z hz, ← hstore b z hz]; exact hl z hz
          · intro j hj; rw [hcount a j hj, hcount b j hj]; exact hc j hj
          · rw [shape_exec_on w ω D hw _ sh hsheq a ha,
                shape_exec_on w ω D hw _ sh hsheq b hb, ht]
  | loop n g body padded ih =>
      intro hwt hs a b h ha hb
      cases hgl : Γ (guardVar g) with
      | low =>
          simp [wt, sitesOK, Label.join, hgl] at hwt hs
          simp only [RunsIn] at ha hb
          simp only [exec]
          apply loopRun_low_on (R := related Γ H) (P := RunsIn w ω D body)
            (cover := CoverIn w D ((shape body).getD []))
          · intro u v huv hu hv; exact ih hwt hs u v huv hu hv
          · intro u v huv
            obtain ⟨hl, hc, ht⟩ := huv
            exact ⟨hl, hc, by simp [ghost, ht]⟩
          · intro u v huv; exact holds_low Γ _ _ huv.1 g hgl
          · exact h
          · exact ha
          · exact hb
      | high =>
          simp [wt, sitesOK, Label.join, hgl] at hwt hs
          obtain ⟨hwb, hpad, hsh⟩ := hwt
          subst hpad
          obtain ⟨x, hx⟩ := Option.isSome_iff_exists.mp hsh
          have hshape : shape (.loop n g body true) = some (rep n x) := by simp [shape, hx]
          have hstore : ∀ st, lowEq Γ st.store (exec w ω (.loop n g body true) st).store := by
            intro st
            simp only [exec]
            apply loopRun_store (P := fun σ => lowEq Γ st.store σ)
            · intro s hs z hz; rw [hs z hz]; exact high_store w ω Γ body hwb s z hz
            · intro s; rfl
            · intro z _; rfl
          have hcount : ∀ st j, H j = false →
              (exec w ω (.loop n g body true) st).count j = st.count j := by
            intro st j hj
            simp only [exec]
            apply loopRun_count (P := fun c => c j = st.count j)
            · intro s hs'; rw [high_count w ω Γ H body hs s j hj]; exact hs'
            · intro s; rfl
            · rfl
          obtain ⟨hl, hc, ht⟩ := h
          refine ⟨?_, ?_, ?_⟩
          · intro z hz; rw [← hstore a z hz, ← hstore b z hz]; exact hl z hz
          · intro j hj; rw [hcount a j hj, hcount b j hj]; exact hc j hj
          · rw [shape_exec_on w ω D hw _ _ hshape a ha,
                shape_exec_on w ω D hw _ _ hshape b hb, ht]

theorem trace_noninterference_on (w : World) (D : RequestDomain) (hw : w.ConformsOn D)
    (Γ : Ctx) (H : Nat → Bool) (s : Stmt) (hwt : wt Γ .low s = true)
    (hs : sitesOK Γ H .low s = true) (σ τ : Store) (hlow : lowEq Γ σ τ)
    (ω : Nat → Nat → Nat)
    (hσ : RunsIn w ω D s ⟨σ, fun _ => 0, []⟩) (hτ : RunsIn w ω D s ⟨τ, fun _ => 0, []⟩) :
    (exec w ω s ⟨σ, fun _ => 0, []⟩).trace = (exec w ω s ⟨τ, fun _ => 0, []⟩).trace :=
  (noninterference_on w D hw ω Γ H s hwt hs ⟨σ, fun _ => 0, []⟩ ⟨τ, fun _ => 0, []⟩
    ⟨hlow, fun _ _ => rfl, rfl⟩ hσ hτ).2.2

/-! #### Theorem 4 on an admitted domain -/

theorem erase_correct_on (w : World) (D : RequestDomain) (ht : w.TransparentOn D)
    (ω : Nat → Nat → Nat) :
    ∀ (s : Stmt), capsOK s = true →
      ∀ a b, sameData a b → RunsIn w ω D s a →
        sameData (exec w ω s a) (exec w ω (erase s) b) := by
  intro s
  induction s with
  | skip => intro _ a b h _; exact h
  | seq x y ihx ihy =>
      intro hc a b h ha
      simp [capsOK] at hc
      obtain ⟨hxa, hya⟩ := ha
      have hx := ihx hc.1 a b h hxa
      exact ihy hc.2 _ _ hx hya
  | call i x m k e p =>
      intro hk a b h ha
      obtain ⟨hs, hc⟩ := h
      cases p with
      | none => simp [erase, exec, sameData, hs, hc]
      | some tn =>
          obtain ⟨T, N⟩ := tn
          simp [capsOK] at hk
          have hr : evalE a.store e = evalE b.store e := by rw [hs]
          have hd : D m T N (evalE a.store e) := ha
          simp [erase, exec, sameData, hs, hc, ht m k T N _ _ hk (hr ▸ hd)]
  | tool x t e => intro _ a b h _; obtain ⟨hs, hc⟩ := h; simp [erase, exec, sameData, hs, hc]
  | dummy => intro _ a b h _; exact h
  | dummyTool => intro _ a b h _; exact h
  | ite g x y ihx ihy =>
      intro hc a b h ha
      simp [capsOK] at hc
      have hg : holds a.store g = holds b.store g := by rw [h.1]
      by_cases hh : holds a.store g = true
      · have hb : holds b.store g = true := by rw [← hg]; exact hh
        simp [RunsIn, hh] at ha
        simp [erase, exec, hh, hb]; exact ihx hc.1 a b h ha
      · have hb : ¬ holds b.store g = true := by rw [← hg]; exact hh
        simp [RunsIn, hh] at ha
        simp [erase, exec, hh, hb]; exact ihy hc.2 a b h ha
  | loop n g body padded ih =>
      intro hc a b h ha
      simp [capsOK] at hc
      simp only [RunsIn] at ha
      simp only [erase, exec]
      apply loopRun_rel2_on (R := sameData) (P := RunsIn w ω D body)
        (cover := CoverIn w D ((shape body).getD []))
      · intro u v huv hu; exact ih hc u v huv hu
      · intro u v huv; exact huv
      · intro u v huv; exact huv
      · intro u v huv; rw [huv.1]
      · exact h
      · exact ha

/-! #### Theorem 5 on an admitted domain -/

theorem shape_usage_exact_on (w : World) (D : RequestDomain) (hw : w.ConformsOn D)
    (ω : Nat → Nat → Nat) (p : Stmt) (sh : List Event) (hs : shape p = some sh)
    (σ : Store) (hrun : RunsIn w ω D p ⟨σ, fun _ => 0, []⟩) (m : String) :
    usage m (exec w ω p ⟨σ, fun _ => 0, []⟩).trace = usage m sh := by
  rw [shape_exec_on w ω D hw p sh hs _ hrun]
  rfl

theorem shape_budget_sound_on (w : World) (D : RequestDomain) (hw : w.ConformsOn D)
    (ω : Nat → Nat → Nat) (p : Stmt) (sh : List Event) (hs : shape p = some sh)
    (σ : Store) (hrun : RunsIn w ω D p ⟨σ, fun _ => 0, []⟩)
    (budget : String → Nat × Nat × Nat) (hb : ∀ m, Within (usage m sh) (budget m)) :
    ∀ m, Within (usage m (exec w ω p ⟨σ, fun _ => 0, []⟩).trace) (budget m) := by
  intro m
  rw [shape_usage_exact_on w D hw ω p sh hs σ hrun m]
  exact hb m

/-! #### Certified end-to-end statements

These combine the source-independent checks (`validateProgram`,
`staticCertificate`) with the domain-restricted serving contracts. The input
guard `boundedStore` is the only run-time premise; no trajectory predicate,
global conformance or global transparency remains. -/

theorem validateProgram_parts (Γ : Ctx) (orig padded : Stmt)
    (hv : validateProgram Γ orig padded = true) :
    clean (erase padded) = clean (erase orig) ∧ wt Γ .low padded = true ∧
      sitesOK Γ (fun i => (highSites Γ .low padded).contains i) .low padded = true ∧
      capsOK padded = true := by
  simp only [validateProgram, validate, Bool.and_eq_true] at hv
  obtain ⟨⟨⟨he, hwt⟩, hs⟩, hcap⟩ := hv
  exact ⟨by simpa using he, hwt, hs, hcap⟩

/-- Certified usage noninterference (restricted-domain Theorem 3). -/
theorem certified_noninterference (w : World) (b : Envelope) (hb : b.Sound w)
    (hw : w.ConformsOn (envelopeDomain w b)) (v : ValueBounds) (Γ : Ctx)
    (orig padded : Stmt) (hv : validateProgram Γ orig padded = true)
    (hc : staticCertificate w b v padded = true)
    (σ τ : Store) (hσ : boundedStore b v σ) (hτ : boundedStore b v τ)
    (hlow : lowEq Γ σ τ) (ω : Nat → Nat → Nat) :
    (exec w ω padded ⟨σ, fun _ => 0, []⟩).trace =
      (exec w ω padded ⟨τ, fun _ => 0, []⟩).trace := by
  obtain ⟨_, hwt, hs, _⟩ := validateProgram_parts Γ orig padded hv
  exact trace_noninterference_on w _ hw Γ _ padded hwt hs σ τ hlow ω
    (static_certificate_implies_RunsIn w b hb v padded hc σ hσ ω)
    (static_certificate_implies_RunsIn w b hb v padded hc τ hτ ω)

/-- Certified noninterference stated over declared secret inputs. -/
theorem certified_secret_inputs_sound (w : World) (b : Envelope) (hb : b.Sound w)
    (hw : w.ConformsOn (envelopeDomain w b)) (v : ValueBounds) (Γ : Ctx)
    (orig padded : Stmt) (secrets : List Var) (hsec : ∀ x, x ∈ secrets → Γ x = .high)
    (hv : validateProgram Γ orig padded = true)
    (hc : staticCertificate w b v padded = true)
    (σ τ : Store) (hσ : boundedStore b v σ) (hτ : boundedStore b v τ)
    (hdiff : ∀ x, x ∉ secrets → σ x = τ x) (ω : Nat → Nat → Nat) :
    (exec w ω padded ⟨σ, fun _ => 0, []⟩).trace =
      (exec w ω padded ⟨τ, fun _ => 0, []⟩).trace := by
  apply certified_noninterference w b hb hw v Γ orig padded hv hc σ τ hσ hτ _ ω
  intro x hx
  apply hdiff x
  intro hmem
  rw [hsec x hmem] at hx
  cases hx

/-- Certified functional preservation (restricted-domain Theorem 4). -/
theorem certified_preservation (w : World) (b : Envelope) (hb : b.Sound w)
    (ht : w.TransparentOn (envelopeDomain w b)) (v : ValueBounds) (Γ : Ctx)
    (orig padded : Stmt) (hv : validateProgram Γ orig padded = true)
    (hc : staticCertificate w b v padded = true)
    (σ : Store) (hσ : boundedStore b v σ) (ω : Nat → Nat → Nat) :
    (exec w ω padded ⟨σ, fun _ => 0, []⟩).store =
      (exec w ω (erase orig) ⟨σ, fun _ => 0, []⟩).store := by
  obtain ⟨he, _, _, hcap⟩ := validateProgram_parts Γ orig padded hv
  let st : St := ⟨σ, fun _ => 0, []⟩
  have hrun := static_certificate_implies_RunsIn w b hb v padded hc σ hσ ω
  have h1 := erase_correct_on w _ ht ω padded hcap st st ⟨rfl, rfl⟩ hrun
  have h2 := clean_data w ω (erase padded) st st ⟨rfl, rfl⟩
  have h3 := clean_data w ω (erase orig) st st ⟨rfl, rfl⟩
  rw [he] at h2
  exact h1.1.trans (h2.1.trans h3.1.symm)

/-- Certified per-model budget admission (restricted-domain Theorem 5). -/
theorem certified_budget_sound (w : World) (b : Envelope) (hb : b.Sound w)
    (hw : w.ConformsOn (envelopeDomain w b)) (v : ValueBounds)
    (p : Stmt) (sh : List Event) (hs : shape p = some sh)
    (hc : staticCertificate w b v p = true)
    (σ : Store) (hσ : boundedStore b v σ) (ω : Nat → Nat → Nat)
    (budget : String → Nat × Nat × Nat) (hbud : ∀ m, Within (usage m sh) (budget m)) :
    ∀ m, Within (usage m (exec w ω p ⟨σ, fun _ => 0, []⟩).trace) (budget m) :=
  shape_budget_sound_on w _ hw ω p sh hs σ
    (static_certificate_implies_RunsIn w b hb v p hc σ hσ ω) budget hbud

/-- The certified shape is the exact trace for every bounded store and tape. -/
theorem certified_shape_exact (w : World) (b : Envelope) (hb : b.Sound w)
    (hw : w.ConformsOn (envelopeDomain w b)) (v : ValueBounds)
    (p : Stmt) (sh : List Event) (hs : shape p = some sh)
    (hc : staticCertificate w b v p = true)
    (σ : Store) (hσ : boundedStore b v σ) (ω : Nat → Nat → Nat) :
    (exec w ω p ⟨σ, fun _ => 0, []⟩).trace = sh := by
  rw [shape_exec_on w ω _ hw p sh hs _
    (static_certificate_implies_RunsIn w b hb v p hc σ hσ ω)]
  rfl

#print axioms noninterference_on
#print axioms trace_noninterference_on
#print axioms erase_correct_on
#print axioms shape_budget_sound_on
#print axioms certified_noninterference
#print axioms certified_secret_inputs_sound
#print axioms certified_preservation
#print axioms certified_budget_sound
#print axioms certified_shape_exact

/-! #### Non-vacuity: a non-truncating padder meets the restricted premises

`padWorld` counts characters, pads by appending filler and never truncates.
It satisfies `ConformsOn` and `TransparentOn` for every envelope domain whose
tokenizer is this character count, yet it violates the global `Conforms` used
by the original statements of Theorems 3 and 5. The restricted theorems are
therefore strictly more applicable, and their premises are satisfiable by a
world with the physical behaviour of the isolated-padding adapter. -/

def padWorld : World where
  tok := fun _ r => r.data.length
  gen := fun _ _ k _ => ⟨List.replicate k 'x'⟩
  forced := fun _ _ _ N => ⟨List.replicate N 'x'⟩
  view := fun _ k r => ⟨r.data.take k⟩
  padReq := fun _ T r => ⟨r.data ++ List.replicate (T - r.data.length) '.'⟩
  outTok := fun _ r => r.data.length
  toolFn := fun _ r => r
  dummyReq := "."

theorem padWorld_conformsOn (b : Envelope) : padWorld.ConformsOn (envelopeDomain padWorld b) := by
  intro m T N r hd
  have hle : r.data.length ≤ T := hd.1
  refine ⟨?_, ?_⟩
  · show (r.data ++ List.replicate (T - r.data.length) '.').length = T
    simp [List.length_append, List.length_replicate]; omega
  · intro c; show (List.replicate N 'x').length = N; simp

theorem padWorld_transparentOn (D : RequestDomain) : padWorld.TransparentOn D := by
  intro m k T N r c hk _
  show (⟨(List.replicate N 'x').take k⟩ : String) = ⟨List.replicate k 'x'⟩
  rw [List.take_replicate, Nat.min_eq_left hk]

theorem padWorld_not_globally_conforming : ¬ padWorld.Conforms := by
  intro h
  have := h.1 "m" 0 "ab"
  simp [padWorld] at this

#print axioms padWorld_conformsOn
#print axioms padWorld_transparentOn
#print axioms padWorld_not_globally_conforming

end OrchLang.Shape
