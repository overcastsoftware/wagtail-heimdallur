import { useCallback, useState } from "react";

import { proofreadText } from "../api";
import type { ProofreadingResult } from "../types";

interface ProofreadButtonProps {
  text: string;
  language: string;
  onResult: (result: ProofreadingResult) => void;
  onError?: (message: string) => void;
}

export function ProofreadButton({
  text,
  language,
  onResult,
  onError
}: ProofreadButtonProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleClick = useCallback(async () => {
    setIsLoading(true);
    try {
      onResult(await proofreadText(text, language));
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "Proofreading failed");
    } finally {
      setIsLoading(false);
    }
  }, [language, onError, onResult, text]);

  return (
    <button
      type="button"
      className="heimdallur-toolbar-button"
      disabled={isLoading}
      onClick={handleClick}
    >
      {isLoading ? "Proofreading" : "Proofread"}
    </button>
  );
}
