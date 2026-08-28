# PD Agent v0.8 - I16 Knowledge Pack Refreeze

## Decision

The v0.8 canonical Knowledge Pack identity is:

`9f1ef7ac14fa63b79aa8ef3decd1fce232729b4eefee6f2292382db4f3f4f3a5`

It contains `104978` records and is the current identity for I16 operation.

The historical v0.7 identity remains immutable:

`9045db86cf29d54f526a918be95c74cc37db87597bcc443cfbdb6f396ca04ef1`

It is not rewritten or reinterpreted.

## Reason

The v0.8 RFC requires `retrieved_at` to remain observable provenance but to be
excluded from canonical `KnowledgeRecord` identity. The resulting pack
identity therefore differs from the historical v0.7 identity.

## Determinism Evidence

The controlled host gate produced two independent materializations:

- Pack A: `9f1ef7ac14fa63b79aa8ef3decd1fce232729b4eefee6f2292382db4f3f4f3a5`
- Pack B: `9f1ef7ac14fa63b79aa8ef3decd1fce232729b4eefee6f2292382db4f3f4f3a5`
- Records A/B: `104978`
- Loader A/B: `PASS`
- Current pack deterministic: `YES`
- Historical pack match: `NO`

The source artifacts and environment were unchanged. The current I16 loader
must validate the refrozen pack after the identity correction; no new
canonical freeze is declared by this document alone.

The controlled host evidence was produced under:

`C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.8-i16-current-pack-1fdf3904544846eb8336c49e2a7f09a7`

The independently validated current snapshots are `pack` and
`pack-B-current` below that root. Both passed the real loader after the
identity correction.

## Boundaries

This record changes no v0.7 historical evidence, task, provider, acceptance,
fixture or scheduler contract. I16 live remains unauthorized until a separate
preflight confirms the current pack and ledger.
