import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { LanguagePairSelector } from "./LanguagePairSelector";

test("LanguagePairSelector renders fetched pairs", async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      translation: {
        language_pairs: [
          { source_language: "is", target_language: "en" }
        ]
      }
    })
  });
  const onSelect = jest.fn();

  render(<LanguagePairSelector onSelect={onSelect} />);

  await screen.findByRole("option", { name: "is to en" });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));

  await waitFor(() =>
    expect(onSelect).toHaveBeenCalledWith({
      source_language: "is",
      target_language: "en"
    })
  );
});
