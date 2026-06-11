import type { DiffAnnotation } from "../types";

interface AnnotationPopoverProps {
  annotation: DiffAnnotation;
  onAccept: (annotation: DiffAnnotation) => void;
  onDismiss: (annotation: DiffAnnotation) => void;
}

export function AnnotationPopover({
  annotation,
  onAccept,
  onDismiss
}: AnnotationPopoverProps) {
  return (
    <div className="heimdallur-popover" role="dialog" aria-label="Proofreading suggestion">
      <dl>
        <dt>Original</dt>
        <dd>{annotation.orig_string}</dd>
        <dt>Suggestion</dt>
        <dd>{annotation.changed_string}</dd>
        <dt>Type</dt>
        <dd>{annotation.change_type}</dd>
      </dl>
      <div className="heimdallur-actions">
        <button type="button" onClick={() => onAccept(annotation)}>
          Accept
        </button>
        <button type="button" onClick={() => onDismiss(annotation)}>
          Dismiss
        </button>
      </div>
    </div>
  );
}
