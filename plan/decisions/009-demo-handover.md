# Decision 009: Demonstration handover and release scope

Date: 22 September 2026. Application `0.9.0`; schema stays `0005`. The user authorized the next phase, PH-09, including live Azure verification already authorized for this MVP.

## Acceptance reports the implemented scope

PH-09 verifies the existing five-family desktop demo, documents restart/recovery and packages a reproducible runtime. It does not silently implement or waive the incomplete PH-05 standalone manual workflow. The original release classifications remain 30 required, three partial and 19 deferred. Every item now has an explicit result and evidence link. AC-03, AC-04, AC-16 and AC-45 remain partial; their missing behavior is recorded in [follow-up work](../Follow_ups.md).

The five live case families include intentional pending/transfer outcomes. A successful name update still needs a classification handoff; an acknowledged bankruptcy handoff is a transfer; EFT clarification still requires consent. These do not count as closed cases. Tests and live evaluations inspect actual records and retain failed draft proposals, rather than equating model output with completion.

This handover can be complete while the broader original MVP definition remains incomplete. The coding plan retains that distinction. Production use and business-policy signoffs are outside this local synthetic release.

## Bundle boundary

`scripts/package-demo.ps1` builds a new timestamped archive from an explicit file allowlist. It includes application source, migrations, locked dependencies, synthetic runtime data and presenter guides, with a SHA-256 manifest. It excludes `.env`, local databases, live evidence, development tests, the original Office files and their private path registry. The extracted app creates a new database and uses the recipient's own model configuration.

The bundle is for running and demonstrating the app. Maintenance commands that reconcile/rebuild original source data and the complete engineering test suite belong to the original workspace. Those source dependencies are documented; they are not bypassed or silently marked verified when sources are absent.

The rehearsal installs from the bundle into a new directory, seeds through the documented script, builds, starts on the runbook's alternate ports and completes a real Azure-driven browser case. Secrets are supplied to the backend process only for that rehearsal; the extracted `.env` stays placeholder-only. Final bundle verification checks the tested application files against the archive and scans for configured Azure values. Documentation may be finalized after the rehearsal without changing tested application behavior.

## Verification evidence

[PH-09](../checkpoints/PH-09.md) records the full offline checks, all five live workflow cases, live partial-failure recovery, PDF review, package/setup/restart rehearsal and local timing observations. Model source remains `live_azure`; deterministic regression evidence is separately identified. Model configuration is recorded by its existing fingerprint and limits, without resource/deployment credentials. Observed local timings are not production SLAs.
