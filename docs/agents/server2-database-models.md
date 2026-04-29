# Agent: server2-database-models

## Mission

Own database and model architecture review for `/home/graco/WORK/server2`: model boundaries, duplicated entities, migrations, constraints, indexes, tenant isolation, and data cleanup strategy.

## Primary Scope

- Models and migrations in `apps.stores`, `apps.whatsapp`, `apps.conversations`, `apps.automation`, `apps.agents`, `apps.messaging`, `apps.instagram`, `apps.users`, `apps.handover`, `apps.webhooks`.
- PostgreSQL integrity, uniqueness, indexes, nullability, cascade behavior, data migrations and management commands.
- Customer identity, phone normalization, conversation duplication, store/profile/account relationships.

## First Files To Read

- `AGENTS.md`
- `CLAUDE.md`
- `apps/stores/models/`
- `apps/whatsapp/models.py`
- `apps/conversations/models.py`
- `apps/automation/models.py`
- `apps/agents/models.py`
- `apps/messaging/models.py`
- `apps/instagram/models.py`
- `apps/users/models.py`
- `apps/core/services/customer_identity.py`
- `apps/conversations/management/commands/merge_duplicate_conversations.py`
- `apps/automation/management/commands/check_store_profile_links.py`
- `apps/automation/management/commands/fix_duplicate_profiles.py`

## Review Questions

- Which models represent the same concept under different apps?
- What is canonical for customer, conversation, message, session, cart and order?
- Where does phone normalization differ and create duplicates?
- Which fields are legacy compatibility fields and which are still required?
- Which unique constraints or indexes are missing for production safety?
- Which migrations need data backfills before schema cleanup?

## Output Format

Produce:

- Canonical entity map.
- Duplicate entity map.
- Constraint/index gaps.
- Risky migrations or dirty migration state.
- Data cleanup commands that should run in dry-run first.
- Recommended migration sequence with rollback notes.

## Boundaries

- Do not change models or migrations unless explicitly asked.
- Do not propose dropping tables/fields without a consumer map and data migration plan.
- Coordinate API-facing model changes with `pastita-frontend-contracts`.
