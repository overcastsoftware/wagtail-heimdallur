import type { PropsWithChildren } from "react";

import type { DiffAnnotation } from "../types";

interface AnnotationDecoratorProps extends PropsWithChildren {
  annotation: DiffAnnotation;
  onSelect?: (annotation: DiffAnnotation) => void;
}

export function AnnotationDecorator({
  annotation,
  children,
  onSelect
}: AnnotationDecoratorProps) {
  return (
    <mark
      className="heimdallur-annotation"
      data-change-type={annotation.change_type}
      tabIndex={0}
      onClick={() => onSelect?.(annotation)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect?.(annotation);
        }
      }}
    >
      {children}
    </mark>
  );
}
