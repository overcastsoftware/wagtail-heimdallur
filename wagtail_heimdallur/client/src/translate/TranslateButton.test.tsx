import { fireEvent, render, screen } from "@testing-library/react";

import { TranslateButton } from "./TranslateButton";

test("TranslateButton opens the selector flow", () => {
  const onOpen = jest.fn();
  render(<TranslateButton onOpen={onOpen} />);

  fireEvent.click(screen.getByRole("button", { name: "Translate" }));

  expect(onOpen).toHaveBeenCalled();
});
