# Upstream source custody and offline reproduction

The integration includes two representations of the same upstream revision:

- `upstream_snapshot/`: all 23 tracked files copied byte for byte. The original
  MIT license and copyright notice remain in `upstream_snapshot/LICENSE`.
- `upstream_c08f710.bundle`: a local Git bundle containing the pinned commit
  and its complete ancestor history. It supports a clean checkout with the
  original commit and tree IDs, without contacting a server.

Upstream is [Onyeka Ogbonna's agent-incident-triage](https://github.com/codewithkachi/agent-incident-triage),
commit `c08f710acfeefe233329df613fe8358eaac5f350`, tree
`2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02`. File identities are recorded in
[`UPSTREAM_MANIFEST.json`](UPSTREAM_MANIFEST.json). The bundle SHA-256 is
`deb487b425c49d95c39cd9ff2d689dc56401f66ffd44f7ae17fbe9a691849080`.

The snapshot is suitable for standard-library AST inspection and independent
source-protocol replay. It has no `.git` directory. The direct execution and
concurrency harnesses also verify Git commit/tree/worktree identity, so give
them a checkout cloned from the bundle:

```sh
git clone --no-checkout integrations/incident_triage/upstream_c08f710.bundle /tmp/incident-triage-offline
git -C /tmp/incident-triage-offline checkout --detach c08f710acfeefe233329df613fe8358eaac5f350
```

Install the separately supplied `requirements.lock` in the optional virtual
environment, then pass `/tmp/incident-triage-offline` to the runtime harnesses
with `--upstream`. Dependency installation needs a package source; the
experiments themselves use the pinned mock and block outbound network calls.
The bundled snapshot alone does not include third-party dependencies.

The source is inspected and executed unchanged. Instrumentation records the
model boundary, imposes a declared concurrency schedule, or supplies a fixed
response for a repair probe. Source mutations used to challenge an analyzer
are separately labeled experimental mutations and are never substituted for
the pinned upstream execution.

The primary agent independently cloned this bundle and reproduced the
concurrency report byte for byte. The record is
[`concurrency/results/root_reproduction.json`](concurrency/results/root_reproduction.json).
The full original study has its own
[`results/root_reproduction.json`](results/root_reproduction.json). These
are distinct records from the compiler's frozen 44-stage manifest.
