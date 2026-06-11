import { applyAnnotationCorrection } from "./correction";

test("applyAnnotationCorrection replaces the original substring", () => {
  expect(
    applyAnnotationCorrection("halló heimu", {
      orig_start_idx: 6,
      orig_end_idx: 11,
      orig_string: "heimu",
      changed_start_idx: 6,
      changed_end_idx: 12,
      changed_string: "heimur",
      change_type: "spelling"
    })
  ).toBe("halló heimur");
});
