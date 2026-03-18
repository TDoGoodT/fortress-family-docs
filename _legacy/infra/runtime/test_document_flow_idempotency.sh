#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(realpath "$(cd "$(dirname "$0")/../.." && pwd)")"
cd "${REPO_ROOT}"

HOUSEHOLD_ID="${FORTRESS_TEST_HOUSEHOLD_ID:-11111111-1111-5111-8111-111111111111}"
TEST_ROOT="${FORTRESS_TEST_TMP_ROOT:-$(mktemp -d /tmp/fortress_document_flow_idempotency.XXXXXX)}"
INBOX_DIR="${TEST_ROOT}/inbox"
RAW_DIR="${TEST_ROOT}/raw"
TEST_FILE="${INBOX_DIR}/test-doc.txt"

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

psql_row() {
  local sql="$1"
  docker compose exec -T postgres psql -X -q -A -t -F '|' -U fortress -d fortress -v ON_ERROR_STOP=1 -c "${sql}"
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

printf 'hello fortress\nidempotency line\n' > "${TEST_FILE}"

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

before_counts="$(psql_row "SELECT (SELECT COUNT(*) FROM ingestion.raw_record WHERE run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM ingestion.normalized_record WHERE run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM ingestion.canonical_handoff_request WHERE run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM core.canonical_handoff_receipt r JOIN ingestion.canonical_handoff_request chr ON chr.handoff_request_id = r.handoff_request_id WHERE chr.run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM core.document d JOIN ingestion.canonical_handoff_request chr ON chr.target_entity_id = d.document_id WHERE chr.run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM public.event_ledger WHERE correlation_id = '${RUN_ID}'::uuid AND aggregate_type = 'core.document' AND event_type = 'core.document.created'), (SELECT COUNT(*) FROM query.household_documents q JOIN ingestion.canonical_handoff_request chr ON chr.target_entity_id = q.document_id WHERE chr.run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM (SELECT document_id, COUNT(*) FROM query.household_documents GROUP BY document_id HAVING COUNT(*) > 1) dup);")"

infra/runtime/promote_filesystem_documents.sh "${RUN_ID}"
infra/runtime/emit_ingestion_events.sh "${RUN_ID}"
processor_rerun_output="$(infra/runtime/process_document_handoffs.sh)"
printf '%s\n' "${processor_rerun_output}"

after_counts="$(psql_row "SELECT (SELECT COUNT(*) FROM ingestion.raw_record WHERE run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM ingestion.normalized_record WHERE run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM ingestion.canonical_handoff_request WHERE run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM core.canonical_handoff_receipt r JOIN ingestion.canonical_handoff_request chr ON chr.handoff_request_id = r.handoff_request_id WHERE chr.run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM core.document d JOIN ingestion.canonical_handoff_request chr ON chr.target_entity_id = d.document_id WHERE chr.run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM public.event_ledger WHERE correlation_id = '${RUN_ID}'::uuid AND aggregate_type = 'core.document' AND event_type = 'core.document.created'), (SELECT COUNT(*) FROM query.household_documents q JOIN ingestion.canonical_handoff_request chr ON chr.target_entity_id = q.document_id WHERE chr.run_id = '${RUN_ID}'::uuid), (SELECT COUNT(*) FROM (SELECT document_id, COUNT(*) FROM query.household_documents GROUP BY document_id HAVING COUNT(*) > 1) dup);")"

assert_eq "${before_counts}" "${after_counts}" "rerun should not create duplicates or extra rows"

if ! printf '%s\n' "${processor_rerun_output}" | grep -q "No eligible document handoffs found in core.ledger_contract_document_created"; then
  fail_assertion "processor rerun should report no eligible document handoffs" "No eligible document handoffs found in core.ledger_contract_document_created" "${processor_rerun_output}"
fi

echo "PASS: document flow idempotency"
echo "run_id=${RUN_ID}"
echo "counts=${after_counts}"
