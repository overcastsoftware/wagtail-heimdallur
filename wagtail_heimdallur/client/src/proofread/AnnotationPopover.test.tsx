import { fireEvent, render, screen } from "@testing-library/react";

import { AnnotationPopover } from "./AnnotationPopover";

const annotation = {
  orig_start_idx: 0,
  orig_end_idx: 4,
  orig_string: "test",
  changed_start_idx: 0,
  changed_end_idx: 5,
  changed_string: "tests",
  change_type: "grammar"
};

test("AnnotationPopover accepts and dismisses suggestions", () => {
  const onAccept = jest.fn();
  const onDismiss = jest.fn();
  render(
    <AnnotationPopover
      annotation={annotation}
      onAccept={onAccept}
      onDismiss={onDismiss}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "Accept" }));
  fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

  expect(onAccept).toHaveBeenCalledWith(annotation);
  expect(onDismiss).toHaveBeenCalledWith(annotation);
});
