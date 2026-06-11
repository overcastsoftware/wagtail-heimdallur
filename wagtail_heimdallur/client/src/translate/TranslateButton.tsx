import { useCallback, useState } from "react";

interface TranslateButtonProps {
  onOpen: () => void;
}

export function TranslateButton({ onOpen }: TranslateButtonProps) {
  const [isOpen, setIsOpen] = useState(false);

  const handleClick = useCallback(() => {
    setIsOpen(true);
    onOpen();
  }, [onOpen]);

  return (
    <button
      type="button"
      className="heimdallur-toolbar-button"
      aria-expanded={isOpen}
      onClick={handleClick}
    >
      Translate
    </button>
  );
}
