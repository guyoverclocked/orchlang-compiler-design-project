# Offline protocol amendments and failures

23 October 2026. Do not present these checks as untouched preregistration or
independent human review. Seeds, endpoints, census and exclusions are unchanged.

1. The first clean v1 run stopped before external outcomes because working and
   committed corpus-manifest bytes differed under Windows newline conversion.
   The source builder now writes LF; `.gitattributes` preserves raw bytes.
2. The clean v3 snapshot, `6f325be2d00b8f617b09fb3f7f3f50b4e8f91f82`, passed CPU
   checks. Its external run stopped at `pf-ner.orch` with two P001 diagnostics:
   expected input name, found `text`; expected expression, found `text`.
   `text` is a reserved keyword. This is an authored projection-construction
   error, not evidence that the original workflow fails or a successful unsafe
   rejection. The aborting runner did not flush partial raw records; preceding
   case outcomes from that attempt are therefore not used as final data.
3. Corrected only that identifier to `document` and its matching reference,
   regenerated the manifest hash, and checked that all 11 corrected source files
   parse/check. The census, bounds, call structure and exclusion policy did not
   change. Added per-command partial-record persistence to the external runner.
   A new clean snapshot freezes this amendment before the complete rerun.

The first complete successful amended run, if obtained, is the reportable one.
It is a protocol-amended offline engineering experiment. It is not a held-out
corpus evaluation and does not support significance or provider claims.
