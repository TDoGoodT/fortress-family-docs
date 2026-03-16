#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: infra/runtime/intake_filesystem_inbox.sh [inbox_path]

Manual polling intake for the controlled filesystem inbox capability.

Environment:
  FORTRESS_INBOX_PATH        Default inbox directory (used if arg not provided)
  FORTRESS_RAW_STORAGE_DIR   Existing approved raw storage directory (required)

Notes:
  - Zero-file polls do not create an ingestion.run
  - Event emission is not automatic; use infra/runtime/emit_ingestion_events.sh <run_id>
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

INBOX_PATH_INPUT="${1:-${FORTRESS_INBOX_PATH:-$HOME/FortressInbox}}"
RAW_STORAGE_DIR_INPUT="${FORTRESS_RAW_STORAGE_DIR:-}"

if [ -z "${RAW_STORAGE_DIR_INPUT}" ]; then
  echo "ERROR: FORTRESS_RAW_STORAGE_DIR is required" >&2
  exit 1
fi

if [ ! -d "${INBOX_PATH_INPUT}" ] || [ ! -r "${INBOX_PATH_INPUT}" ]; then
  echo "ERROR: inbox path must exist and be readable: ${INBOX_PATH_INPUT}" >&2
  exit 1
fi

if [ ! -d "${RAW_STORAGE_DIR_INPUT}" ] || [ ! -w "${RAW_STORAGE_DIR_INPUT}" ]; then
  echo "ERROR: raw storage directory must exist and be writable: ${RAW_STORAGE_DIR_INPUT}" >&2
  exit 1
fi

INBOX_PATH="$(realpath "${INBOX_PATH_INPUT}")"
RAW_STORAGE_DIR="$(realpath "${RAW_STORAGE_DIR_INPUT}")"
REPO_ROOT="$(realpath "$(cd "$(dirname "$0")/../.." && pwd)")"

case "${INBOX_PATH}" in
  "${REPO_ROOT}"|"${REPO_ROOT}"/*)
    echo "ERROR: inbox path must remain outside Fortress repository tree: ${INBOX_PATH}" >&2
    exit 1
    ;;
esac

if ! docker compose ps postgres >/dev/null 2>&1; then
  echo "ERROR: postgres service is not available via docker compose" >&2
  exit 1
fi

FILES=()
while IFS= read -r file_path; do
  FILES+=("${file_path}")
done < <(find "${INBOX_PATH}" -type f -print | sort)
TOTAL_DISCOVERED="${#FILES[@]}"

if [ "${TOTAL_DISCOVERED}" -eq 0 ]; then
  echo "No eligible files in inbox: ${INBOX_PATH}"
  echo "Zero-file poll: no ingestion.run created"
  exit 0
fi

json_details() {
  python - "$@" <<'PY'
import json,sys
pairs=sys.argv[1:]
out={}
for p in pairs:
  k,v=p.split('=',1)
  out[k]=v
print(json.dumps(out,separators=(',',':')))
PY
}

resolve_source_id() {
  docker compose exec -T postgres psql -X -q -A -t -U fortress -d fortress -v ON_ERROR_STOP=1 \
    -v source_key="${INBOX_PATH}" <<'SQL' | tr -d '[:space:]'
WITH ins AS (
  INSERT INTO ingestion.source (source_type, source_key)
  VALUES ('filesystem_inbox', :'source_key')
  ON CONFLICT (source_type, source_key) DO NOTHING
  RETURNING source_id
)
SELECT source_id::text FROM ins
UNION ALL
SELECT s.source_id::text
FROM ingestion.source s
WHERE s.source_type = 'filesystem_inbox'
  AND s.source_key = :'source_key'
LIMIT 1;
SQL
}

create_run_id() {
  local source_id="$1"
  docker compose exec -T postgres psql -X -q -A -t -U fortress -d fortress -v ON_ERROR_STOP=1 \
    -v source_id="${source_id}" <<'SQL' | tr -d '[:space:]'
INSERT INTO ingestion.run (source_id)
VALUES (:'source_id'::uuid)
RETURNING run_id::text;
SQL
}

append_run_state() {
  local run_id="$1"
  local state="$2"
  docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 \
    -v run_id="${run_id}" -v state="${state}" <<'SQL' >/dev/null
WITH next_seq AS (
  SELECT COALESCE(MAX(state_seq), 0) + 1 AS state_seq
  FROM ingestion.run_state
  WHERE run_id = :'run_id'::uuid
)
INSERT INTO ingestion.run_state (run_id, state_seq, state)
SELECT :'run_id'::uuid, next_seq.state_seq, :'state'::text
FROM next_seq;
SQL
}

next_error_attempt() {
  local run_id="$1"
  local stage="$2"
  docker compose exec -T postgres psql -X -q -A -t -U fortress -d fortress -v ON_ERROR_STOP=1 \
    -v run_id="${run_id}" -v stage="${stage}" <<'SQL' | tr -d '[:space:]'
SELECT COALESCE(MAX(e.attempt), 0) + 1
FROM ingestion.error e
WHERE e.run_id = :'run_id'::uuid
  AND e.stage = :'stage'::text
  AND e.subject_type = 'filesystem_path'
  AND e.subject_id IS NULL;
SQL
}

insert_ingestion_error() {
  local run_id="$1"; shift
  local stage="$1"; shift
  local error_class="$1"; shift
  local error_code="$1"; shift
  local details_json="$1"

  local attempt
  attempt="$(next_error_attempt "${run_id}" "${stage}")"
  [ -z "${attempt}" ] && attempt="1"

  local fingerprint_hex
  fingerprint_hex="$(printf '%s' "${stage}|filesystem_path||${error_class}|${error_code}|${details_json}" | sha256sum | awk '{print $1}')"

  docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 \
    -v run_id="${run_id}" -v stage="${stage}" -v error_class="${error_class}" -v error_code="${error_code}" \
    -v attempt="${attempt}" -v fingerprint_hex="${fingerprint_hex}" -v details_json="${details_json}" <<'SQL' >/dev/null
INSERT INTO ingestion.error (
  run_id,
  stage,
  error_class,
  error_code,
  attempt,
  subject_type,
  subject_id,
  is_retryable,
  details,
  error_fingerprint_sha256
)
VALUES (
  :'run_id'::uuid,
  :'stage'::text,
  :'error_class'::text,
  :'error_code'::text,
  :'attempt'::integer,
  'filesystem_path',
  NULL,
  true,
  :'details_json'::jsonb,
  decode(:'fingerprint_hex', 'hex')
);
SQL
}

insert_raw_object() {
  local run_id="$1"
  local source_id="$2"
  local locator="$3"
  local sha_hex="$4"

  docker compose exec -T postgres psql -X -q -A -t -U fortress -d fortress -v ON_ERROR_STOP=1 \
    -v run_id="${run_id}" -v source_id="${source_id}" -v locator="${locator}" -v sha_hex="${sha_hex}" <<'SQL' | tr -d '[:space:]'
WITH ins AS (
  INSERT INTO ingestion.raw_object (run_id, source_id, object_locator, content_sha256)
  VALUES (:'run_id'::uuid, :'source_id'::uuid, :'locator'::text, decode(:'sha_hex', 'hex'))
  ON CONFLICT (source_id, object_locator, content_sha256) DO NOTHING
  RETURNING raw_object_id
)
SELECT raw_object_id::text FROM ins LIMIT 1;
SQL
}

SOURCE_ID="$(resolve_source_id)"
if [ -z "${SOURCE_ID}" ]; then
  echo "ERROR: failed to resolve ingestion source id" >&2
  exit 1
fi

RUN_ID="$(create_run_id "${SOURCE_ID}")"
if [ -z "${RUN_ID}" ]; then
  echo "ERROR: failed to create ingestion run" >&2
  exit 1
fi

append_run_state "${RUN_ID}" "started"

registered=0
duplicates=0
failures=0
processed=0

for file_path in "${FILES[@]}"; do
  processed=$((processed + 1))
  abs_file="$(realpath "${file_path}")"
  locator="filesystem://${abs_file}"

  if [ ! -r "${abs_file}" ]; then
    failures=$((failures + 1))
    insert_ingestion_error "${RUN_ID}" "filesystem_inbox_intake" "io_error" "source_unreadable" \
      "$(json_details file_path="${abs_file}" reason="unreadable_source")"
    append_run_state "${RUN_ID}" "file_failed"
    continue
  fi

  src_sha="$(sha256sum "${abs_file}" | awk '{print $1}')"
  dest_path="${RAW_STORAGE_DIR}/${src_sha}"
  tmp_path="${dest_path}.tmp.$$"

  if ! cp -f "${abs_file}" "${tmp_path}"; then
    failures=$((failures + 1))
    insert_ingestion_error "${RUN_ID}" "filesystem_inbox_intake" "io_error" "copy_failed" \
      "$(json_details file_path="${abs_file}" reason="copy_failed")"
    rm -f "${tmp_path}" || true
    append_run_state "${RUN_ID}" "file_failed"
    continue
  fi

  dst_sha="$(sha256sum "${tmp_path}" | awk '{print $1}')"
  if [ "${src_sha}" != "${dst_sha}" ]; then
    failures=$((failures + 1))
    insert_ingestion_error "${RUN_ID}" "filesystem_inbox_intake" "integrity_error" "copy_hash_mismatch" \
      "$(json_details file_path="${abs_file}" reason="hash_mismatch" source_sha256="${src_sha}" copied_sha256="${dst_sha}")"
    rm -f "${tmp_path}" || true
    append_run_state "${RUN_ID}" "file_failed"
    continue
  fi

  mv -f "${tmp_path}" "${dest_path}"

  raw_object_id="$(insert_raw_object "${RUN_ID}" "${SOURCE_ID}" "${locator}" "${src_sha}")"
  if [ -z "${raw_object_id}" ]; then
    duplicates=$((duplicates + 1))
    append_run_state "${RUN_ID}" "file_duplicate"
    continue
  fi

  registered=$((registered + 1))
  append_run_state "${RUN_ID}" "file_registered"
done

if [ "${failures}" -gt 0 ]; then
  append_run_state "${RUN_ID}" "completed_with_errors"
else
  append_run_state "${RUN_ID}" "completed"
fi

echo "Controlled filesystem inbox intake completed"
echo "inbox_path=${INBOX_PATH}"
echo "raw_storage_dir=${RAW_STORAGE_DIR}"
echo "run_id=${RUN_ID}"
echo "discovered=${TOTAL_DISCOVERED}"
echo "processed=${processed}"
echo "registered=${registered}"
echo "duplicates=${duplicates}"
echo "failures=${failures}"
echo "event_emission=operator_triggered"
echo "next_step=infra/runtime/emit_ingestion_events.sh ${RUN_ID}"
