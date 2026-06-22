export { proofreadText, fetchProofreadingLanguages } from "./api";
export {
  acceptAllSuggestions,
  acceptSuggestion,
  applyProofreadingResults,
  buildBlockSuggestions,
  countProofreadEntities,
  detectContentLanguage,
  getProofreadableBlocks,
  loadProofreadingLanguages,
  removeProofreadEntities
} from "./proofread/draftailProofread";
export { registerProofreadPlugins } from "./proofread/registerProofread";

import { registerProofreadPlugins } from "./proofread/registerProofread";

registerProofreadPlugins();
