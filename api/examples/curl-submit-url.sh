#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_TOKEN:?Set GITHUB_TOKEN}"
: "${OWNER:?Set OWNER}"
: "${REPO:?Set REPO}"
: "${SOURCE_URL:?Set SOURCE_URL}"

JOB_ID="job_$(python -c 'import uuid; print(uuid.uuid4().hex)')"
FILENAME="${FILENAME:-input.bin}"
REF="${REF:-main}"
export JOB_ID FILENAME REF

curl --fail-with-body --silent --show-error \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/process.yml/dispatches" \
  -d "$(python -c 'import json,os; print(json.dumps({"ref":os.environ["REF"],"return_run_details":True,"inputs":{"job_id":os.environ["JOB_ID"],"source_type":"url","source_url":os.environ["SOURCE_URL"],"filename":os.environ["FILENAME"]}}))')"
