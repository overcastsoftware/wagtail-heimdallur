import type { ProofreadingResult, TranslationPair } from "./types";

async function postJson<T>(url: string, payload: object): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
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

export async function translateText(
  text: string,
  sourceLanguage: string,
  targetLanguage: string
): Promise<string> {
  const data = await postJson<{ translated_text: string }>("/api/heimdallur/translate/", {
    text,
    source_language: sourceLanguage,
    target_language: targetLanguage
  });
  return data.translated_text;
}

export async function fetchLanguagePairs(): Promise<TranslationPair[]> {
  const response = await fetch("/api/heimdallur/languages/");
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.error?.message || "Could not load supported languages");
  }
  return data.translation.language_pairs as TranslationPair[];
}
