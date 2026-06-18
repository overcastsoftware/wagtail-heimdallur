import {
  applyAnnotationCorrectionToRaw,
  applyCorrectedBlockText,
  getProofreadableBlocks
} from "./richTextProofreader";

const raw = JSON.stringify({
  blocks: [
    {
      key: "a",
      text: "Halló heimr",
      type: "unstyled",
      depth: 0,
      inlineStyleRanges: [],
      entityRanges: []
    },
    {
      key: "b",
      text: "",
      type: "unstyled",
      depth: 0,
      inlineStyleRanges: [],
      entityRanges: []
    }
  ],
  entityMap: {}
});

test("getProofreadableBlocks extracts non-empty Draftail blocks", () => {
  expect(getProofreadableBlocks(raw)).toEqual([
    {
      key: "a",
      index: 0,
      text: "Halló heimr"
    }
  ]);
});

test("applyCorrectedBlockText updates a Draftail block", () => {
  const updated = JSON.parse(applyCorrectedBlockText(raw, "a", "Halló heimur"));

  expect(updated.blocks[0].text).toBe("Halló heimur");
  expect(updated.blocks[1].text).toBe("");
});

test("applyAnnotationCorrectionToRaw updates a Draftail block annotation", () => {
  const updated = JSON.parse(
    applyAnnotationCorrectionToRaw(raw, "a", {
      orig_start_idx: 6,
      orig_end_idx: 11,
      orig_string: "heimr",
      changed_start_idx: 6,
      changed_end_idx: 12,
      changed_string: "heimur",
      change_type: "spelling"
    })
  );

  expect(updated.blocks[0].text).toBe("Halló heimur");
});
