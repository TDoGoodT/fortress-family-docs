#!/usr/bin/env bash
set -euo pipefail

# Fortress DB Migration Runner (Controlled Execution Path)
#
# Behavior:
# - Enumerate infra/db migrations in deterministic lexical order.
# - Apply each migration with fail-fast (psql -v ON_ERROR_STOP=1).
# - Require that each applied migration inserts its row into public.schema_migrations.
# - Safe to re-run (skips already-applied versions).
#
# Requirements:
# - PGURI must be set (canonical): host-driven psql execution.
#
# Notes:
# - Only runs files matching: ^[0-9][0-9][0-9][a-z]?_.*\.sql$
# - Excludes: *.obsolete, phase1_schema_only.sql

if [[ -z "${PGURI:-}" ]]; then
  echo "ERROR: PGURI is not set. Example:"
  echo "  export PGURI='host=127.0.0.1 port=5432 dbname=fortress user=fortress password=fortress_dev_password'"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Deterministic list of migration candidates (macOS-compatible)
MIGRATIONS=()

# BSD find prints full paths; we sort deterministically, then take basenames
while IFS= read -r path; do
  f="$(basename "$path")"

  case "$f" in
    phase1_schema_only.sql) continue ;;
    *.obsolete) continue ;;
    [0-9][0-9][0-9]_*\.sql) MIGRATIONS+=("$f") ;;
    [0-9][0-9][0-9][a-z]_*.sql) MIGRATIONS+=("$f") ;;
    *) : ;;
  esac
done < <(find "$ROOT_DIR" -maxdepth 1 -type f -name "*.sql" | LC_ALL=C sort)

if [[ "${#MIGRATIONS[@]}" -eq 0 ]]; then
  echo "No migrations found under $ROOT_DIR"
  exit 0
fi

psql_base=(psql "$PGURI" -X -v ON_ERROR_STOP=1 -P pager=off)

applied=()
skipped=()
bootstrap_end_index=-1

schema_migrations_exists() {
  "${psql_base[@]}" -tAc "select to_regclass('public.schema_migrations') is not null;" | tr -d '[:space:]'
}

recorded_in_schema_migrations() {
  local version="$1"
  "${psql_base[@]}" -tAc "select 1 from public.schema_migrations where version = '$version' limit 1;" | tr -d '[:space:]'
}

bootstrap_schema_migrations_if_needed() {
  local exists
  exists="$(schema_migrations_exists)" || {
    echo "ERROR: failed checking whether public.schema_migrations exists"
    exit 1
  }

  if [[ "$exists" == "t" ]]; then
    return
  fi

  echo "BOOTSTRAP public.schema_migrations via canonical migration path"

  # Governance boundary:
  # - 008b_create_schema_migrations.sql is the bootstrap boundary.
  # - No migrations may be inserted before this boundary.

  for i in "${!MIGRATIONS[@]}"; do
    local f="${MIGRATIONS[$i]}"

    echo "APPLY  $f (bootstrap)"
    "${psql_base[@]}" -f "$ROOT_DIR/$f"
    applied+=("$f")

    if [[ "$f" == "008b_create_schema_migrations.sql" ]]; then
      bootstrap_end_index="$i"
      break
    fi
  done

  if [[ "$bootstrap_end_index" -lt 0 ]]; then
    echo "ERROR: bootstrap migration 008b_create_schema_migrations.sql not found"
    exit 1
  fi

  exists="$(schema_migrations_exists)" || {
    echo "ERROR: failed verifying public.schema_migrations after bootstrap"
    exit 1
  }

  if [[ "$exists" != "t" ]]; then
    echo "ERROR: bootstrap completed but public.schema_migrations still does not exist"
    exit 1
  fi

  for i in $(seq 0 "$bootstrap_end_index"); do
    local f="${MIGRATIONS[$i]}"
    local recorded
    recorded="$(recorded_in_schema_migrations "$f")" || {
      echo "ERROR: failed verifying schema_migrations bootstrap entry for $f"
      exit 1
    }

    if [[ "$recorded" != "1" ]]; then
      echo "ERROR: bootstrap migration applied but NOT recorded in public.schema_migrations: $f"
      echo "Ruling: FAIL (bootstrap governance invariant broken)"
      exit 1
    fi
  done

  echo
}

echo "Fortress Migration Runner"
echo "DB: PGURI set (host-driven psql)"
echo "Dir: $ROOT_DIR"
echo "Count: ${#MIGRATIONS[@]}"
echo

bootstrap_schema_migrations_if_needed

start_index=0
if [[ "$bootstrap_end_index" -ge 0 ]]; then
  start_index=$((bootstrap_end_index + 1))
fi

for ((i = start_index; i < ${#MIGRATIONS[@]}; i++)); do
  f="${MIGRATIONS[$i]}"

  already="$(recorded_in_schema_migrations "$f")" || {
    echo "ERROR: failed checking schema_migrations for $f"
    exit 1
  }

  if [[ "$already" == "1" ]]; then
    echo "SKIP   $f (already in public.schema_migrations)"
    skipped+=("$f")
    continue
  fi

  echo "APPLY  $f"
  "${psql_base[@]}" -f "$ROOT_DIR/$f"

  recorded="$(recorded_in_schema_migrations "$f")" || {
    echo "ERROR: failed verifying schema_migrations after applying $f"
    exit 1
  }

  if [[ "$recorded" != "1" ]]; then
    echo "ERROR: migration applied but NOT recorded in public.schema_migrations: $f"
    echo "Ruling: FAIL (governance invariant broken)"
    exit 1
  fi

  applied+=("$f")
done

echo
echo "Summary"
echo "Applied: ${#applied[@]}"
for x in ${applied[@]:-}; do echo "  + $x"; done
echo "Skipped: ${#skipped[@]}"
for x in ${skipped[@]:-}; do echo "  - $x"; done
