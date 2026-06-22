import { getDraftailRegistry } from "./draftailGlobals";
import {
  ClearProofreadingControl,
  PROOFREAD_CLEAR_CONTROL_TYPE,
  PROOFREAD_CONTROL_TYPE,
  PROOFREAD_ENTITY_TYPE,
  ProofreadControl,
  ProofreadSource,
  SuggestionDecorator,
  loadProofreadingLanguages
} from "./draftailProofread";

// Register the proofreading Draftail plugins against Wagtail's editor. Safe to
// call when Draftail is unavailable (e.g. in tests); it simply no-ops.
export function registerProofreadPlugins(): boolean {
  const draftail = getDraftailRegistry();
  if (typeof draftail.registerPlugin !== "function") {
    return false;
  }

  draftail.registerPlugin(
    {
      type: PROOFREAD_ENTITY_TYPE,
      source: ProofreadSource,
      decorator: SuggestionDecorator
    },
    "entityTypes"
  );
  draftail.registerPlugin(
    { type: PROOFREAD_CONTROL_TYPE, inline: ProofreadControl },
    "controls"
  );
  draftail.registerPlugin(
    { type: PROOFREAD_CLEAR_CONTROL_TYPE, inline: ClearProofreadingControl },
    "controls"
  );

  // Warm the supported-languages lookup so the control can decide synchronously
  // whether to render by the time editors mount.
  loadProofreadingLanguages();

  return true;
}
