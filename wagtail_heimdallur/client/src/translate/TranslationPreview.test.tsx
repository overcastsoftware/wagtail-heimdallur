import { fireEvent, render, screen } from "@testing-library/react";

import { TranslationPreview } from "./TranslationPreview";

test("TranslationPreview supports accept and cancel", () => {
  const onAccept = jest.fn();
  const onCancel = jest.fn();
  render(
    <TranslationPreview
      translatedText="hello"
      onAccept={onAccept}
      onCancel={onCancel}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "Accept" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  expect(onAccept).toHaveBeenCalledWith("hello");
  expect(onCancel).toHaveBeenCalled();
});
