import type { DiffAnnotation } from "../types";

export function applyAnnotationCorrection(text: string, annotation: DiffAnnotation): string {
  return [
    text.slice(0, annotation.orig_start_idx),
    annotation.changed_string,
    text.slice(annotation.orig_end_idx)
  ].join("");
}
