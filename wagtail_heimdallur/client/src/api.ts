import type { ProofreadingResult } from "./types";

async function postJson<T>(url: string, payload: object): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };
  const csrfToken = getCookie("csrftoken");
  if (csrfToken) {
    headers["X-CSRFToken"] = csrfToken;
  }

  const response = await fetch(url, {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });
  const data = await parseJsonResponse(response);
  if (!response.ok) {
    throw new Error(data?.error?.message || "Heimdallur request failed");
  }
  return data as T;
}

export function proofreadText(text: string, language: string): Promise<ProofreadingResult> {
  return postJson<ProofreadingResult>("/api/heimdallur/proofread/", {
    text,
    language
  });
}

export async function fetchProofreadingLanguages(): Promise<string[]> {
  const response = await fetch("/api/heimdallur/languages/");
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.error?.message || "Could not load supported languages");
  }
  return (data?.proofreading?.languages ?? []) as string[];
}

function getCookie(name: string): string {
  const cookies = document.cookie ? document.cookie.split(";") : [];
  for (const cookie of cookies) {
    const [rawKey, ...valueParts] = cookie.trim().split("=");
    if (rawKey === name) {
      return decodeURIComponent(valueParts.join("="));
    }
  }
  return "";
}

async function parseJsonResponse(response: Response): Promise<any> {
  const contentType = response.headers.get("Content-Type") || "";
  if (!contentType.includes("application/json")) {
    return {};
  }
  return response.json();
}
