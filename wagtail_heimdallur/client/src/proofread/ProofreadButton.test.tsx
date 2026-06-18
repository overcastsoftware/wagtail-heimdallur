import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ProofreadButton } from "./ProofreadButton";

test("ProofreadButton triggers API call and returns result", async () => {
  document.cookie = "csrftoken=test-token";
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => ({
      original_text: "text",
      corrected_text: "text",
      annotations: []
    })
  });
  const onResult = jest.fn();

  render(<ProofreadButton text="text" language="is" onResult={onResult} />);
  fireEvent.click(screen.getByRole("button", { name: "Proofread" }));

  await waitFor(() => expect(onResult).toHaveBeenCalled());
  expect(global.fetch).toHaveBeenCalledWith(
    "/api/heimdallur/proofread/",
    expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      headers: expect.objectContaining({
        "Content-Type": "application/json",
        "X-CSRFToken": "test-token"
      })
    })
  );
});
