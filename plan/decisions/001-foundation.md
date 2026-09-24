# Implementation baseline: Phase 1

Date: 22 September 2026. Status: adopted for the authorized Phase 1 implementation.

The user approved implementation of Phase 1 after reviewing the coding plan and confirmed Azure Foundry OpenAI models already deployed in their resource group. The session was interrupted by a power cut; work resumed from the existing files and completed dependency installation.

| Decision | Baseline |
| --- | --- |
| Scope | Implement PH-01 and record its PH-00 prerequisites. PH-02 through PH-09 remain future phases. |
| Existing layout | Preserve source Office files under `docs/` and planning documents under `plan/`. New decisions/checkpoints are also under `plan/`. Repair source-document links from the moved BRD. |
| Release assumptions | Retain the five-family internal presenter/reviewer demo proposal. One small synthetic foundation sample is enough for Phase 1 verification; it is not the full Phase 2 fixture set. |
| Frontend | React/TypeScript/Vite with a local worklist and case detail/activity view. Exact resolved versions are in `frontend/package-lock.json`. |
| Backend | FastAPI/Pydantic, SQLAlchemy, SQLite, Alembic. Exact runtime/dev versions are in `backend/requirements.lock`; schema revision starts at `0001`. |
| Persistence | SQLite foreign keys and transactions; UTC timestamp storage; text identifiers; integer monetary minor units; optimistic case revisions and stable mutation IDs. |
| Model provider | Azure Foundry / Azure OpenAI. Prepare an API-key configuration for the resource's OpenAI v1 base URL and deployment name. No public OpenAI endpoint fallback or assumed model name. |
| Credentials | Preserve root `.env`; commit only `.env.example`. User will provide values later. Phase 1 does not make model calls, even if values are present. |
| API contract | Commit OpenAPI and generated frontend types. Future run/review mutation endpoints are explicitly unavailable until their phases. |
| Worker foundation | Persist lease owner/token/expiry and checkpoint context. A single active worker lease is claimed atomically; expired ownership requires reconciliation and old tokens cannot renew. No worker is started in this phase. |
| Source policies | Existing BRD gaps remain unresolved unless separately settled. No live-system actions or fabricated business-policy decisions are introduced. |

Official configuration sources: [OpenAI libraries](https://developers.openai.com/api/docs/libraries), [Azure endpoint and deployment guidance](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/switching-endpoints?view=foundry-classic).
