import { useEffect, useState } from "react";

import { fetchLanguagePairs } from "../api";
import type { TranslationPair } from "../types";

interface LanguagePairSelectorProps {
  onSelect: (pair: TranslationPair) => void;
  onError?: (message: string) => void;
}

export function LanguagePairSelector({ onSelect, onError }: LanguagePairSelectorProps) {
  const [pairs, setPairs] = useState<TranslationPair[]>([]);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    let isActive = true;
    fetchLanguagePairs()
      .then((loadedPairs) => {
        if (!isActive) {
          return;
        }
        setPairs(loadedPairs);
        if (loadedPairs.length > 0) {
          setSelected(pairKey(loadedPairs[0]));
        }
      })
      .catch((error) => {
        onError?.(error instanceof Error ? error.message : "Could not load languages");
      });
    return () => {
      isActive = false;
    };
  }, [onError]);

  const selectedPair = pairs.find((pair) => pairKey(pair) === selected);

  return (
    <div className="heimdallur-language-selector">
      <select
        value={selected}
        onChange={(event) => setSelected(event.target.value)}
        aria-label="Language pair"
      >
        {pairs.map((pair) => (
          <option key={pairKey(pair)} value={pairKey(pair)}>
            {pair.source_language} to {pair.target_language}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={!selectedPair}
        onClick={() => selectedPair && onSelect(selectedPair)}
      >
        Continue
      </button>
    </div>
  );
}

function pairKey(pair: TranslationPair): string {
  return `${pair.source_language}:${pair.target_language}`;
}
