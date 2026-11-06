// Minimal Node.js 20+ example for a bot backend.
// Set GITHUB_TOKEN in the environment. Do not send the token to end users.

import { createReadStream } from "node:fs";
import { randomUUID } from "node:crypto";

const API = "https://api.github.com";
const OWNER = process.env.GITHUB_OWNER;
const REPO = process.env.GITHUB_REPO;
const REF = process.env.GITHUB_REF || "main";
const TOKEN = process.env.GITHUB_TOKEN;
const MAX_UPLOAD_BYTES = Number(process.env.FILESPLITTER_MAX_INPUT_BYTES || "1900000000");

if (!OWNER || !REPO || !TOKEN) {
  throw new Error("Set GITHUB_OWNER, GITHUB_REPO and GITHUB_TOKEN");
}

async function github(path, options = {}) {
  const url = path.startsWith("https://") ? path : `${API}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${TOKEN}`,
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "FileSplitter-API-JS-Example/1.0",
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub API ${response.status}: ${body.slice(0, 1000)}`);
  }
  return response;
}

// Input by direct URL.
export async function submitUrl(url, filename) {
  const jobId = `job_${randomUUID().replaceAll("-", "")}`;
  const inferredName = decodeURIComponent(new URL(url).pathname.split("/").pop() || "input.bin");
  filename ||= inferredName;
  const response = await github(`/repos/${OWNER}/${REPO}/actions/workflows/process.yml/dispatches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ref: REF,
      return_run_details: true,
      inputs: { job_id: jobId, source_type: "url", source_url: url, filename },
    }),
  });
  return { job_id: jobId, ...(await response.json()) };
}

// Input by local file. Creates a temporary draft Release and uploads the file first.
export async function submitFile(filePath) {
  const { stat } = await import("node:fs/promises");
  const { basename } = await import("node:path");
  const jobId = `job_${randomUUID().replaceAll("-", "")}`;
  const fileStat = await stat(filePath);
  if (!fileStat.isFile() || fileStat.size < 1 || fileStat.size > MAX_UPLOAD_BYTES) {
    throw new Error(`Input must be a file between 1 byte and ${MAX_UPLOAD_BYTES} bytes`);
  }
  const filename = basename(filePath).replace(/[^A-Za-z0-9._ -]/g, "_").slice(0, 180) || "input.bin";
  const tag = `fs-input-${jobId}`;
  const created = await (await github(`/repos/${OWNER}/${REPO}/releases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag_name: tag, name: `FileSplitter input ${jobId}`, body: `filesplitter_created_at=${Math.floor(Date.now() / 1000)}`, draft: true, prerelease: false }),
  })).json();

  try {
    const uploadUrl = created.upload_url.split("{", 1)[0];
    const stream = createReadStream(filePath);
    const asset = await (await github(`${uploadUrl}?name=${encodeURIComponent(filename)}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream", "Content-Length": String(fileStat.size) },
      body: stream,
      duplex: "half",
    })).json();
    if (!asset?.id) throw new Error("GitHub did not return the uploaded input asset ID");

    const dispatched = await (await github(`/repos/${OWNER}/${REPO}/actions/workflows/process.yml/dispatches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ref: REF,
        return_run_details: true,
        inputs: {
          job_id: jobId,
          source_type: "release_asset",
          input_release_id: String(created.id),
          input_asset_id: String(asset.id),
          filename,
        },
      }),
    })).json();
    return { job_id: jobId, input_release_id: created.id, ...dispatched };
  } catch (error) {
    await github(`/repos/${OWNER}/${REPO}/releases/${created.id}`, { method: "DELETE" }).catch(() => {});
    await github(`/repos/${OWNER}/${REPO}/git/refs/tags/${encodeURIComponent(tag)}`, { method: "DELETE" }).catch(() => {});
    throw error;
  }
}

export async function getStatus(runId) {
  return (await github(`/repos/${OWNER}/${REPO}/actions/runs/${runId}`)).json();
}

export async function getResult(jobId) {
  const tag = `fs-output-${jobId}`;
  const release = await (await github(`/repos/${OWNER}/${REPO}/releases/tags/${encodeURIComponent(tag)}`)).json();
  const asset = release.assets.find((item) => item.name === "response.json");
  if (!asset) throw new Error("response.json not found; check that the workflow completed successfully");
  const response = await github(`/repos/${OWNER}/${REPO}/releases/assets/${asset.id}`, {
    headers: { Accept: "application/octet-stream" },
  });
  return response.json(); // { "parts": ["https://.../part1.zip", ...] }
}
