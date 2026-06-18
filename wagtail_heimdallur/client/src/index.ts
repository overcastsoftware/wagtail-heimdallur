export { proofreadText, translateText, fetchLanguagePairs } from "./api";
export { applyAnnotationCorrection } from "./proofread/correction";
export {
  applyAnnotationCorrectionToRaw,
  applyCorrectedBlockText,
  getProofreadableBlocks,
  initRichTextProofreader
} from "./proofread/richTextProofreader";
export { ProofreadButton } from "./proofread/ProofreadButton";
export { AnnotationDecorator } from "./proofread/AnnotationDecorator";
export { AnnotationPopover } from "./proofread/AnnotationPopover";
export { TranslateButton } from "./translate/TranslateButton";
export { LanguagePairSelector } from "./translate/LanguagePairSelector";
export { TranslationPreview } from "./translate/TranslationPreview";

declare global {
  interface Window {
    WagtailHeimdallur?: object;
  }
}

window.WagtailHeimdallur = {
  ...(window.WagtailHeimdallur || {}),
  applyAnnotationCorrection,
  applyAnnotationCorrectionToRaw,
  applyCorrectedBlockText,
  getProofreadableBlocks,
  initRichTextProofreader
};

import { applyAnnotationCorrection } from "./proofread/correction";
import {
  applyAnnotationCorrectionToRaw,
  applyCorrectedBlockText,
  getProofreadableBlocks,
  initRichTextProofreader
} from "./proofread/richTextProofreader";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => initRichTextProofreader());
} else {
  initRichTextProofreader();
}
