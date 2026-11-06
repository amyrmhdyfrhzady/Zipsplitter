#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_TOKEN:?Set GITHUB_TOKEN}"
: "${OWNER:?Set OWNER}"
: "${REPO:?Set REPO}"
: "${FILE_PATH:?Set FILE_PATH}"

REF="${REF:-main}"
JOB_ID="job_$(python -c 'import uuid; print(uuid.uuid4().hex)')"
FILENAME="$(basename "$FILE_PATH")"
TAG="fs-input-${JOB_ID}"
CREATED_AT="$(date +%s)"
export REF JOB_ID FILENAME TAG CREATED_AT
API="https://api.github.com/repos/${OWNER}/${REPO}"

CREATE_JSON="$(curl --fail-with-body --silent --show-error \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  -H "Content-Type: application/json" \
  "${API}/releases" \
  -d "$(python -c 'import json,os; print(json.dumps({"tag_name":os.environ["TAG"],"name":"FileSplitter input "+os.environ["JOB_ID"],"body":"filesplitter_created_at="+os.environ["CREATED_AT"],"draft":True,"prerelease":False}))')")"

RELEASE_ID="$(printf '%s' "$CREATE_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
UPLOAD_URL="$(printf '%s' "$CREATE_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)["upload_url"].split("{",1)[0])')"

UPLOAD_JSON="$(curl --fail-with-body --silent --show-error \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@${FILE_PATH}" \
  "${UPLOAD_URL}?name=$(python -c 'import os,urllib.parse; print(urllib.parse.quote(os.environ["FILENAME"]))')")"
ASSET_ID="$(printf '%s' "$UPLOAD_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

export JOB_ID REF RELEASE_ID ASSET_ID FILENAME
curl --fail-with-body --silent --show-error \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  -H "Content-Type: application/json" \
  "${API}/actions/workflows/process.yml/dispatches" \
  -d "$(python -c 'import json,os; print(json.dumps({"ref":os.environ["REF"],"return_run_details":True,"inputs":{"job_id":os.environ["JOB_ID"],"source_type":"release_asset","input_release_id":os.environ["RELEASE_ID"],"input_asset_id":os.environ["ASSET_ID"],"filename":os.environ["FILENAME"]}}))')"
