#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(realpath "$(cd "$(dirname "$0")/../.." && pwd)")"
cd "${REPO_ROOT}"

HOUSEHOLD_ID="${FORTRESS_TEST_HOUSEHOLD_ID:-11111111-1111-5111-8111-111111111111}"
TEST_ROOT="${FORTRESS_TEST_TMP_ROOT:-$(mktemp -d /tmp/fortress_document_flow_e2e.XXXXXX)}"
INBOX_DIR="${TEST_ROOT}/inbox"
RAW_DIR="${TEST_ROOT}/raw"
TEST_FILE="${INBOX_DIR}/test-doc.txt"
EXPECTED_TITLE="test-doc.txt"

fail_assertion() {
  local message="$1"
  local expected="$2"
  local actual="$3"
  echo "ASSERTION FAILED: ${message}" >&2
  echo "expected=${expected}" >&2
  echo "actual=${actual}" >&2
  exit 1
}

assert_eq() {
  local expected="$1"
  local actual="$2"
  local message="$3"
  if [ "${expected}" != "${actual}" ]; then
    fail_assertion "${message}" "${expected}" "${actual}"
  fi
}

psql_value() {
  local sql="$1"
  docker compose exec -T postgres psql -X -q -A -t -U fortress -d fortress -v ON_ERROR_STOP=1 -c "${sql}" | tr -d '[:space:]'
}

reset_database_state() {
  docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL' >/dev/null
TRUNCATE TABLE
  core.canonical_handoff_receipt,
  core.document,
  core.account,
  core.task,
  core.person,
  ingestion.error,
  ingestion.canonical_handoff_request,
  ingestion.normalized_record,
  ingestion.raw_record,
  ingestion.raw_object,
  ingestion.run_state,
  ingestion.run,
  ingestion.source,
  public.event_ledger
RESTART IDENTITY CASCADE;
SQL
}

mkdir -p "${INBOX_DIR}" "${RAW_DIR}"
trap 'rm -rf "${TEST_ROOT}"' EXIT

reset_database_state

printf 'hello fortress\na test line\n' > "${TEST_FILE}"

export FORTRESS_RAW_STORAGE_DIR="${RAW_DIR}"
export FORTRESS_DEFAULT_HOUSEHOLD_ID="${HOUSEHOLD_ID}"

intake_output="$(infra/runtime/intake_filesystem_inbox.sh "${INBOX_DIR}")"
printf '%s\n' "${intake_output}"

RUN_ID="$(printf '%s\n' "${intake_output}" | awk -F= '/^run_id=/{print $2}')"
if [ -z "${RUN_ID}" ]; then
  fail_assertion "run_id should be present in intake output" "non-empty run_id" "empty"
fi

infra/runtime/promote_filesystem_documents.sh "${RUN_ID}"
infra/runtime/emit_ingestion_events.sh "${RUN_ID}"
infra/runtime/process_document_handoffs.sh

document_count="$(psql_value "SELECT COUNT(*) FROM core.document d JOIN ingestion.canonical_handoff_request chr ON chr.target_entity_id = d.document_id WHERE chr.run_id = '${RUN_ID}'::uuid;")"
query_count="$(psql_value "SELECT COUNT(*) FROM query.household_documents q JOIN ingestion.canonical_handoff_request chr ON chr.target_entity_id = q.document_id WHERE chr.run_id = '${RUN_ID}'::uuid;")"
duplicate_count="$(psql_value "SELECT COUNT(*) FROM (SELECT document_id, COUNT(*) FROM query.household_documents GROUP BY document_id HAVING COUNT(*) > 1) dup;")"
created_at_match_count="$(psql_value "SELECT COUNT(*) FROM query.household_documents q JOIN core.document d ON d.document_id = q.document_id JOIN ingestion.canonical_handoff_request chr ON chr.target_entity_id = q.document_id WHERE chr.run_id = '${RUN_ID}'::uuid AND q.created_at = d.created_at;")"

assert_eq "1" "${document_count}" "document should be created in core.document"
assert_eq "1" "${query_count}" "document should appear in query.household_documents"
assert_eq "0" "${duplicate_count}" "query.household_documents should not contain duplicate document_ids"
assert_eq "1" "${created_at_match_count}" "created_at in query.household_documents should match core.document"

projection_output="$(infra/runtime/check_projection_consistency.sh)"
printf '%s\n' "${projection_output}"

if ! printf '%s\n' "${projection_output}" | grep -Eq "missing_aggregate_count[[:space:]]+\\|[[:space:]]+0"; then
  fail_assertion "projection consistency should report missing_aggregate_count = 0" "missing_aggregate_count = 0" "${projection_output}"
fi
if ! printf '%s\n' "${projection_output}" | grep -Eq "orphan_aggregate_count[[:space:]]+\\|[[:space:]]+0"; then
  fail_assertion "projection consistency should report orphan_aggregate_count = 0" "orphan_aggregate_count = 0" "${projection_output}"
fi
if ! printf '%s\n' "${projection_output}" | grep -Eq "field_divergence_count[[:space:]]+\\|[[:space:]]+0"; then
  fail_assertion "projection consistency should report field_divergence_count = 0" "field_divergence_count = 0" "${projection_output}"
fi

echo "PASS: document flow E2E"
echo "run_id=${RUN_ID}"
echo "household_id=${HOUSEHOLD_ID}"
