import { proofreadText } from "../api";
import type { DiffAnnotation, ProofreadingResult } from "../types";

interface RawDraftBlock {
  key: string;
  text: string;
  inlineStyleRanges?: Array<{ offset: number; length: number }>;
  entityRanges?: Array<{ offset: number; length: number }>;
}

interface RawDraftContent {
  blocks?: RawDraftBlock[];
  entityMap?: Record<string, unknown>;
}

interface ProofreadableBlock {
  key: string;
  index: number;
  text: string;
}

interface BlockProofreadingResult {
  block: ProofreadableBlock;
  result: ProofreadingResult;
}

const INITIALIZED_ATTRIBUTE = "data-heimdallur-proofread";

export function initRichTextProofreader(root: ParentNode = document): void {
  const fields = Array.from(
    root.querySelectorAll<HTMLInputElement>("input[data-draftail-input]")
  );

  fields.forEach((field) => {
    if (field.getAttribute(INITIALIZED_ATTRIBUTE) === "true") {
      return;
    }
    field.setAttribute(INITIALIZED_ATTRIBUTE, "true");
    mountProofreadPanel(field);
  });
}

export function getProofreadableBlocks(rawJson: string): ProofreadableBlock[] {
  const content = parseRawContent(rawJson);
  return (content.blocks || [])
    .map((block, index) => ({
      key: block.key,
      index,
      text: block.text || ""
    }))
    .filter((block) => block.text.trim() !== "");
}

export function applyCorrectedBlockText(
  rawJson: string,
  blockKey: string,
  correctedText: string
): string {
  const content = parseRawContent(rawJson);
  const blocks = content.blocks || [];
  const block = blocks.find((candidate) => candidate.key === blockKey);
  if (!block) {
    throw new Error("Could not find the proofread block.");
  }

  const delta = correctedText.length - block.text.length;
  block.text = correctedText;
  block.inlineStyleRanges = adjustRanges(block.inlineStyleRanges || [], 0, delta);
  block.entityRanges = adjustRanges(block.entityRanges || [], 0, delta);
  return JSON.stringify(content);
}

export function applyAnnotationCorrectionToRaw(
  rawJson: string,
  blockKey: string,
  annotation: DiffAnnotation
): string {
  const content = parseRawContent(rawJson);
  const blocks = content.blocks || [];
  const block = blocks.find((candidate) => candidate.key === blockKey);
  if (!block) {
    throw new Error("Could not find the proofread block.");
  }

  const { text, start, end } = applyAnnotationToText(block.text, annotation);
  const delta = text.length - block.text.length;
  block.text = text;
  block.inlineStyleRanges = adjustRanges(block.inlineStyleRanges || [], end, delta);
  block.entityRanges = adjustRanges(block.entityRanges || [], end, delta);
  return JSON.stringify(content);
}

function mountProofreadPanel(field: HTMLInputElement): void {
  const panel = document.createElement("section");
  panel.className = "heimdallur-proofread-panel";
  panel.setAttribute("aria-label", "Heimdallur proofreading");

  const button = document.createElement("button");
  button.type = "button";
  button.className = "heimdallur-toolbar-button";
  button.textContent = "Proofread";

  const status = document.createElement("p");
  status.className = "heimdallur-proofread-status";

  const suggestions = document.createElement("div");
  suggestions.className = "heimdallur-proofread-suggestions";

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Proofreading";
    status.textContent = "";
    suggestions.replaceChildren();

    try {
      const results = await proofreadField(field);
      renderProofreadingResults(field, suggestions, status, results);
    } catch (error) {
      status.textContent =
        error instanceof Error ? error.message : "Proofreading failed.";
    } finally {
      button.disabled = false;
      button.textContent = "Proofread";
    }
  });

  panel.append(button, status, suggestions);
  field.insertAdjacentElement("afterend", panel);
}

async function proofreadField(field: HTMLInputElement): Promise<BlockProofreadingResult[]> {
  const blocks = getProofreadableBlocks(field.value);
  if (!blocks.length) {
    return [];
  }

  const language = getLanguage(field);
  const results = await Promise.all(
    blocks.map(async (block) => ({
      block,
      result: await proofreadText(block.text, language)
    }))
  );
  return results.filter(
    ({ result }) =>
      result.annotations.length > 0 || result.corrected_text !== result.original_text
  );
}

function renderProofreadingResults(
  field: HTMLInputElement,
  container: HTMLElement,
  status: HTMLElement,
  results: BlockProofreadingResult[]
): void {
  if (!results.length) {
    status.textContent = "No proofreading suggestions.";
    return;
  }

  status.textContent = `${results.length} text block${
    results.length === 1 ? "" : "s"
  } with suggestions.`;

  results.forEach(({ block, result }) => {
    const item = document.createElement("article");
    item.className = "heimdallur-proofread-suggestion";

    const original = document.createElement("p");
    original.className = "heimdallur-proofread-original";
    original.textContent = block.text;

    const corrected = document.createElement("p");
    corrected.className = "heimdallur-proofread-corrected";
    corrected.textContent = result.corrected_text;

    const meta = document.createElement("p");
    meta.className = "heimdallur-proofread-meta";
    meta.textContent = `${result.annotations.length} suggestion${
      result.annotations.length === 1 ? "" : "s"
    }`;

    const applyButton = document.createElement("button");
    applyButton.type = "button";
    applyButton.textContent = "Apply corrected text";
    applyButton.addEventListener("click", () => {
      field.value = applyCorrectedBlockText(
        field.value,
        block.key,
        result.corrected_text
      );
      field.dispatchEvent(new Event("input", { bubbles: true }));
      field.dispatchEvent(new Event("change", { bubbles: true }));
      item.remove();
      if (!container.children.length) {
        status.textContent = "All proofreading suggestions applied.";
      }
    });

    item.append(original, corrected, meta, applyButton);
    container.append(item);
  });
}

function parseRawContent(rawJson: string): RawDraftContent {
  try {
    const parsed = JSON.parse(rawJson || "{}") as RawDraftContent;
    return {
      ...parsed,
      blocks: Array.isArray(parsed.blocks) ? parsed.blocks : [],
      entityMap: parsed.entityMap || {}
    };
  } catch (error) {
    throw new Error("Could not parse rich text content for proofreading.");
  }
}

function applyAnnotationToText(text: string, annotation: DiffAnnotation) {
  let start = annotation.orig_start_idx;
  let end = annotation.orig_end_idx;
  if (text.slice(start, end) !== annotation.orig_string) {
    start = text.indexOf(annotation.orig_string);
    end = start + annotation.orig_string.length;
  }
  if (start < 0) {
    throw new Error("Could not locate the proofreading suggestion text.");
  }

  return {
    text: `${text.slice(0, start)}${annotation.changed_string}${text.slice(end)}`,
    start,
    end
  };
}

function adjustRanges<T extends { offset: number; length: number }>(
  ranges: T[],
  replacementEnd: number,
  delta: number
): T[] {
  return ranges.map((range) => {
    if (range.offset >= replacementEnd) {
      return {
        ...range,
        offset: Math.max(0, range.offset + delta)
      };
    }
    return range;
  });
}

function getLanguage(field: HTMLElement): string {
  const closestLanguage = field.closest<HTMLElement>("[lang]")?.lang;
  return (closestLanguage || document.documentElement.lang || "is").split("-")[0] || "is";
}
