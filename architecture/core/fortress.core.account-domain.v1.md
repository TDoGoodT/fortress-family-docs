# fortress.core.account-domain.v1

## Status
ACTIVE

## Canonical
Yes

## Purpose
Define the MVP operational domain specification for `core.account` as a pure identity aggregate.

## Scope
This document defines only the MVP identity boundary of accounts.

In scope:
- canonical account identity
- minimal account fields
- initial create event
- contract trigger
- minimal payload schema
- projection mapping

Out of scope:
- transactions
- balances
- currency logic
- reporting
- reconciliation
- classification analytics

## 1. Canonical Identity

`core.account` represents a canonical identity container for financial activity.

An account is not a ledger and not a balance state.

MVP rule:
- one `account_id` identifies one financial container
- the aggregate stores identity only
- balance and activity are modeled elsewhere

MVP boundary:
- accounts may represent external financial containers
- accounts may represent internal manually tracked containers
- both are treated uniformly as canonical account identities

## 2. MVP Aggregate Fields

The `core.account` MVP aggregate contains only:

- `account_id`
- `household_id`
- `account_label`
- `account_kind`
- `created_at`

Field intent:
- `account_id`: aggregate primary key
- `household_id`: owning household identity
- `account_label`: human-readable identifier
- `account_kind`: bounded MVP account category
- `created_at`: projection-derived creation timestamp

## 3. Canonical Event

The only approved MVP event is:

- `core.account.created`

Aggregate envelope:
- `aggregate_type = 'core.account'`
- `aggregate_id = account_id`
- `event_type = 'core.account.created'`

No update, closure, archival, or balance events are included in MVP.

## 4. Contract Trigger

The approved trigger types for MVP are:

- `account`
- `core.account`

For the minimal validation fixture and normal MVP path, preferred trigger is:

- `account`

## 5. Minimal Payload Schema

The event payload for `core.account.created` contains only:

- `handoff_request_id`
- `normalized_record_id`
- `run_id`
- `source_id`
- `household_id`
- `account_label`
- `account_kind`
- `canonical_record_type`
- `schema_version`

Canonical identity is carried in the event envelope:

- `aggregate_id -> account_id`

## 6. MVP Account Kind Boundary

`account_kind` is required and bounded in MVP to explicit values only:

- `cash_account`
- `investment_account`
- `retirement_account`

No other account kinds are approved in v1.

## 7. Projection Mapping

`core.ledger_projection_account_created` must map:

- `aggregate_id -> account_id`
- `payload.household_id -> household_id`
- `payload.account_label -> account_label`
- `payload.account_kind -> account_kind`
- `event_timestamp -> created_at`

`created_at` is projection-derived and excluded from projection consistency comparison.

## 8. Explicit Non-Scope

The following are explicitly out of scope for `core.account` MVP:

- balances
- transaction history
- statement lines
- currency conversion
- institution enrichment
- ownership percentages
- reporting views
- liquidity calculations
- reconciliation logic
- account lifecycle transitions

## 9. Governing Principle

For MVP:

`core.account` is a pure identity aggregate.

It defines the canonical container to which future financial events may attach.

It does not itself represent money movement, balance truth, or financial reporting state.
