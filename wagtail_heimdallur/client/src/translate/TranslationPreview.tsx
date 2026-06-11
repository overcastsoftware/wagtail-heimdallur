interface TranslationPreviewProps {
  translatedText: string;
  onAccept: (translatedText: string) => void;
  onCancel: () => void;
}

export function TranslationPreview({
  translatedText,
  onAccept,
  onCancel
}: TranslationPreviewProps) {
  return (
    <section className="heimdallur-translation-preview" aria-label="Translation preview">
      <p>{translatedText}</p>
      <div className="heimdallur-actions">
        <button type="button" onClick={() => onAccept(translatedText)}>
          Accept
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}
