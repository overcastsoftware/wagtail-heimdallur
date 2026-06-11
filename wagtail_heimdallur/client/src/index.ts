export { proofreadText, translateText, fetchLanguagePairs } from "./api";
export { applyAnnotationCorrection } from "./proofread/correction";
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
  applyAnnotationCorrection
};

import { applyAnnotationCorrection } from "./proofread/correction";
