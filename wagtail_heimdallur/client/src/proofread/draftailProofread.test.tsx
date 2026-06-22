import React from "react";
import { ContentState, EditorState, type ContentBlock } from "draft-js";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ProofreadingResult } from "../types";

jest.mock("../api", () => ({
  proofreadText: jest.fn(),
  fetchProofreadingLanguages: jest.fn()
}));

import { fetchProofreadingLanguages, proofreadText } from "../api";
import {
  ClearProofreadingControl,
  PROOFREAD_ENTITY_TYPE,
  ProofreadControl,
  ProofreadSource,
  SuggestionDecorator,
  acceptAllSuggestions,
  acceptSuggestion,
  applyProofreadingResults,
  buildBlockSuggestions,
  countProofreadEntities,
  detectContentLanguage,
  detectLanguage,
  getProofreadableBlocks,
  removeProofreadEntities,
  resetProofreadingLanguagesCache
} from "./draftailProofread";

const proofreadTextMock = proofreadText as jest.MockedFunction<
  typeof proofreadText
>;
const fetchProofreadingLanguagesMock =
  fetchProofreadingLanguages as jest.MockedFunction<
    typeof fetchProofreadingLanguages
  >;

function setContentLocale(code: string): void {
  (window as unknown as { wagtailConfig?: { ACTIVE_CONTENT_LOCALE?: string } }).wagtailConfig =
    { ACTIVE_CONTENT_LOCALE: code };
}

function stateFromText(text: string): EditorState {
  return EditorState.createWithContent(ContentState.createFromText(text));
}

function result(partial: Partial<ProofreadingResult> = {}): ProofreadingResult {
  return {
    original_text: "Halló heimr",
    corrected_text: "Halló heimr",
    annotations: [],
    ...partial
  };
}

const spellingResult = result({
  annotations: [
    {
      orig_start_idx: 6,
      orig_end_idx: 11,
      orig_string: "heimr",
      changed_start_idx: 6,
      changed_end_idx: 12,
      changed_string: "heimur",
      change_type: "spelling"
    }
  ]
});

// Two suggestions in "Halló heimr villr".
const twoResult = result({
  annotations: [
    {
      orig_start_idx: 6,
      orig_end_idx: 11,
      orig_string: "heimr",
      changed_start_idx: 6,
      changed_end_idx: 12,
      changed_string: "heimur",
      change_type: "spelling"
    },
    {
      orig_start_idx: 12,
      orig_end_idx: 17,
      orig_string: "villr",
      changed_start_idx: 13,
      changed_end_idx: 19,
      changed_string: "villur",
      change_type: "spelling"
    }
  ]
});

interface CollectedEntity {
  type: string;
  data: Record<string, unknown>;
  text: string;
}

function collectEntities(editorState: EditorState): CollectedEntity[] {
  const content = editorState.getCurrentContent();
  const entities: CollectedEntity[] = [];
  content.getBlocksAsArray().forEach((block: ContentBlock) => {
    const text = block.getText();
    block.findEntityRanges(
      (character) => character.getEntity() !== null,
      (start, end) => {
        const key = block.getEntityAt(start);
        if (!key) {
          return;
        }
        const entity = content.getEntity(key);
        entities.push({
          type: entity.getType(),
          data: entity.getData(),
          text: text.slice(start, end)
        });
      }
    );
  });
  return entities;
}

function firstEntityKey(editorState: EditorState): string {
  const content = editorState.getCurrentContent();
  let key = "";
  content.getBlocksAsArray().some((block: ContentBlock) => {
    block.findEntityRanges(
      (character) => character.getEntity() !== null,
      (start) => {
        key = key || (block.getEntityAt(start) as string);
      }
    );
    return key !== "";
  });
  return key;
}

function allEntityKeys(editorState: EditorState): string[] {
  const content = editorState.getCurrentContent();
  const keys: string[] = [];
  content.getBlocksAsArray().forEach((block: ContentBlock) => {
    block.findEntityRanges(
      (character) => character.getEntity() !== null,
      (start) => {
        const key = block.getEntityAt(start);
        if (key && !keys.includes(key)) {
          keys.push(key);
        }
      }
    );
  });
  return keys;
}

beforeEach(() => {
  proofreadTextMock.mockReset();
  fetchProofreadingLanguagesMock.mockReset();
  fetchProofreadingLanguagesMock.mockResolvedValue(["is"]);
  resetProofreadingLanguagesCache();
  setContentLocale("is");
});

describe("pure helpers", () => {
  test("getProofreadableBlocks skips blank blocks", () => {
    const content = ContentState.createFromText("Halló\n\nheimr");
    const blocks = getProofreadableBlocks(EditorState.createWithContent(content));
    expect(blocks.map((block) => block.text)).toEqual(["Halló", "heimr"]);
  });

  test("buildBlockSuggestions maps annotations", () => {
    expect(buildBlockSuggestions("Halló heimr", spellingResult)).toEqual([
      {
        start: 6,
        end: 11,
        original: "heimr",
        replacement: "heimur",
        changeType: "spelling"
      }
    ]);
  });

  test("buildBlockSuggestions relocates annotations whose indices drifted", () => {
    expect(buildBlockSuggestions("Hér: heimr", spellingResult)).toEqual([
      {
        start: 5,
        end: 10,
        original: "heimr",
        replacement: "heimur",
        changeType: "spelling"
      }
    ]);
  });

  test("buildBlockSuggestions falls back to whole-block correction", () => {
    const suggestions = buildBlockSuggestions(
      "Halló heimr",
      result({ corrected_text: "Halló heimur" })
    );
    expect(suggestions).toEqual([
      {
        start: 0,
        end: 11,
        original: "Halló heimr",
        replacement: "Halló heimur",
        changeType: "edit"
      }
    ]);
  });

  test("applyProofreadingResults applies an entity over the annotation range", () => {
    const editorState = stateFromText("Halló heimr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();

    const { editorState: next, applied } = applyProofreadingResults(editorState, [
      { blockKey, result: spellingResult }
    ]);

    expect(applied).toBe(1);
    expect(collectEntities(next)).toEqual([
      {
        type: PROOFREAD_ENTITY_TYPE,
        data: {
          original: "heimr",
          replacement: "heimur",
          changeType: "spelling"
        },
        text: "heimr"
      }
    ]);
  });

  test("acceptSuggestion replaces the entity range with the correction", () => {
    const editorState = stateFromText("Halló heimr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: spellingResult }
    ]);

    const accepted = acceptSuggestion(highlighted, firstEntityKey(highlighted));

    expect(accepted.getCurrentContent().getPlainText()).toBe("Halló heimur");
    expect(collectEntities(accepted)).toEqual([]);
  });

  test("acceptAllSuggestions applies every correction in one pass", () => {
    const editorState = stateFromText("Halló heimr villr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: twoResult }
    ]);
    expect(countProofreadEntities(highlighted)).toBe(2);

    const applied = acceptAllSuggestions(highlighted);

    expect(applied.getCurrentContent().getPlainText()).toBe("Halló heimur villur");
    expect(countProofreadEntities(applied)).toBe(0);
  });

  test("removeProofreadEntities clears highlights but keeps the text", () => {
    const editorState = stateFromText("Halló heimr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: spellingResult }
    ]);

    const cleared = removeProofreadEntities(highlighted);

    expect(cleared.getCurrentContent().getPlainText()).toBe("Halló heimr");
    expect(collectEntities(cleared)).toEqual([]);
  });

  test("countProofreadEntities counts active highlights", () => {
    const editorState = stateFromText("Halló heimr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    expect(countProofreadEntities(editorState)).toBe(0);
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: spellingResult }
    ]);
    expect(countProofreadEntities(highlighted)).toBe(1);
    expect(countProofreadEntities(removeProofreadEntities(highlighted))).toBe(0);
  });

  test("detectLanguage prefers the closest lang attribute", () => {
    const wrapper = document.createElement("div");
    wrapper.lang = "en-GB";
    const inner = document.createElement("span");
    wrapper.append(inner);
    expect(detectLanguage(inner)).toBe("en");
    expect(detectLanguage(null)).toBe("is");
  });

  test("detectContentLanguage prefers the active content locale", () => {
    setContentLocale("en-GB");
    expect(detectContentLanguage(null)).toBe("en");
  });

  test("detectContentLanguage falls back to DOM detection without a content locale", () => {
    delete (window as unknown as { wagtailConfig?: unknown }).wagtailConfig;
    const el = document.createElement("div");
    el.lang = "pl";
    document.body.append(el);
    expect(detectContentLanguage(el)).toBe("pl");
    el.remove();
  });
});

describe("SuggestionDecorator", () => {
  function renderDecorator() {
    const editorState = stateFromText("Halló heimr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: spellingResult }
    ]);
    const entityKey = firstEntityKey(highlighted);
    const onEdit = jest.fn();
    const onRemove = jest.fn();
    render(
      <SuggestionDecorator
        contentState={highlighted.getCurrentContent()}
        entityKey={entityKey}
        onEdit={onEdit}
        onRemove={onRemove}
      >
        heimr
      </SuggestionDecorator>
    );
    return { entityKey, onEdit, onRemove };
  }

  function renderTwo() {
    const editorState = stateFromText("Halló heimr villr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: twoResult }
    ]);
    const keys = allEntityKeys(highlighted);
    const onEdit = jest.fn();
    render(
      <>
        <SuggestionDecorator
          contentState={highlighted.getCurrentContent()}
          entityKey={keys[0]}
          onEdit={onEdit}
          onRemove={jest.fn()}
        >
          heimr
        </SuggestionDecorator>
        <SuggestionDecorator
          contentState={highlighted.getCurrentContent()}
          entityKey={keys[1]}
          onEdit={jest.fn()}
          onRemove={jest.fn()}
        >
          villr
        </SuggestionDecorator>
      </>
    );
    return { highlighted, keys, onEdit };
  }

  test("opens a popover and accepts via onEdit", () => {
    const { entityKey, onEdit, onRemove } = renderDecorator();

    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "heimr" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("heimur")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Accept suggestion" }));
    expect(onEdit).toHaveBeenCalledWith(entityKey);
    expect(onRemove).not.toHaveBeenCalled();
  });

  test("dismisses via onRemove", () => {
    const { entityKey, onEdit, onRemove } = renderDecorator();
    fireEvent.click(screen.getByRole("button", { name: "heimr" }));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss suggestion" }));
    expect(onRemove).toHaveBeenCalledWith(entityKey);
    expect(onEdit).not.toHaveBeenCalled();
  });

  test("keeps only one popover open at a time", () => {
    renderTwo();
    fireEvent.click(screen.getByRole("button", { name: "heimr" }));
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "villr" }));
    // Opening the second closes the first — still exactly one popover.
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  test("closes the open popover on an outside mousedown", () => {
    renderDecorator();
    fireEvent.click(screen.getByRole("button", { name: "heimr" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("'Accept all' applies every suggestion through the source", () => {
    const { highlighted, keys, onEdit } = renderTwo();
    fireEvent.click(screen.getByRole("button", { name: "heimr" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Accept all suggestions" })
    );
    expect(onEdit).toHaveBeenCalledWith(keys[0]);

    // Draftail then mounts the source for that entity; it applies every
    // suggestion because "Accept all" was requested.
    const onComplete = jest.fn();
    render(
      <ProofreadSource
        editorState={highlighted}
        entityKey={keys[0]}
        onComplete={onComplete}
      />
    );
    const applied = onComplete.mock.calls[0][0] as EditorState;
    expect(applied.getCurrentContent().getPlainText()).toBe("Halló heimur villur");
    expect(countProofreadEntities(applied)).toBe(0);
  });
});

describe("ProofreadControl", () => {
  test("proofreads all blocks and shows a suggestion-count badge", async () => {
    proofreadTextMock.mockResolvedValue(spellingResult);
    let current = stateFromText("Halló heimr");
    const onChange = jest.fn((next: EditorState) => {
      current = next;
    });

    render(
      <ProofreadControl getEditorState={() => current} onChange={onChange} />
    );

    fireEvent.click(await screen.findByRole("button", { name: "Proofread" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    expect(collectEntities(current)).toHaveLength(1);
    expect(proofreadTextMock).toHaveBeenCalledWith("Halló heimr", "is");
    // The badge reflects the number of active suggestions.
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  test("becomes 'Apply all' once suggestions exist and applies them", async () => {
    const editorState = stateFromText("Halló heimr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: spellingResult }
    ]);
    let current = highlighted;
    const onChange = jest.fn((next: EditorState) => {
      current = next;
    });

    render(
      <ProofreadControl getEditorState={() => current} onChange={onChange} />
    );

    const applyButton = await screen.findByRole("button", {
      name: "Apply all suggestions"
    });
    // No re-proofread button while suggestions are pending.
    expect(screen.queryByRole("button", { name: "Proofread" })).toBeNull();
    fireEvent.click(applyButton);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(current.getCurrentContent().getPlainText()).toBe("Halló heimur");
    expect(collectEntities(current)).toEqual([]);
  });

  test("reports backend errors without changing the editor", async () => {
    proofreadTextMock.mockRejectedValue(new Error("Backend unavailable"));
    const editorState = stateFromText("Halló heimr");
    const onChange = jest.fn();

    render(
      <ProofreadControl
        getEditorState={() => editorState}
        onChange={onChange}
      />
    );

    fireEvent.click(await screen.findByRole("button", { name: "Proofread" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Backend unavailable")
    );
    expect(onChange).not.toHaveBeenCalled();
  });

  test("does nothing when there is no text", async () => {
    const onChange = jest.fn();
    render(
      <ProofreadControl getEditorState={() => stateFromText("")} onChange={onChange} />
    );

    fireEvent.click(await screen.findByRole("button", { name: "Proofread" }));

    expect(proofreadTextMock).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("No text to proofread.");
  });

  test("uses the page's content locale for the request", async () => {
    proofreadTextMock.mockResolvedValue(spellingResult);
    // Admin UI is English, but the page is Icelandic content.
    document.documentElement.lang = "en";
    setContentLocale("is");
    let current = stateFromText("Halló heimr");
    const onChange = jest.fn((next: EditorState) => {
      current = next;
    });

    render(
      <ProofreadControl getEditorState={() => current} onChange={onChange} />
    );
    fireEvent.click(await screen.findByRole("button", { name: "Proofread" }));

    await waitFor(() =>
      expect(proofreadTextMock).toHaveBeenCalledWith("Halló heimr", "is")
    );
    document.documentElement.lang = "";
  });

  test("hides when no backend supports the page's content language", async () => {
    setContentLocale("en");
    fetchProofreadingLanguagesMock.mockResolvedValue(["is"]);
    resetProofreadingLanguagesCache();

    render(
      <ProofreadControl
        getEditorState={() => stateFromText("Hello world")}
        onChange={jest.fn()}
      />
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Proofread" })
      ).toBeNull()
    );
    expect(proofreadTextMock).not.toHaveBeenCalled();
  });

  test("shows when a backend supports the page's content language", async () => {
    setContentLocale("is");
    fetchProofreadingLanguagesMock.mockResolvedValue(["is", "en"]);
    resetProofreadingLanguagesCache();

    render(
      <ProofreadControl
        getEditorState={() => stateFromText("Halló heimr")}
        onChange={jest.fn()}
      />
    );

    expect(
      await screen.findByRole("button", { name: "Proofread" })
    ).toBeInTheDocument();
  });
});

describe("ClearProofreadingControl", () => {
  test("removes all proofreading entities", () => {
    const editorState = stateFromText("Halló heimr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: spellingResult }
    ]);
    const onChange = jest.fn();

    render(
      <ClearProofreadingControl
        getEditorState={() => highlighted}
        onChange={onChange}
      />
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Dismiss all proofreading suggestions" })
    );
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(collectEntities(onChange.mock.calls[0][0])).toEqual([]);
  });

  test("renders nothing when there are no suggestions", () => {
    const { container } = render(
      <ClearProofreadingControl
        getEditorState={() => stateFromText("Halló heimr")}
        onChange={jest.fn()}
      />
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("ProofreadSource", () => {
  test("applies only this suggestion by default", () => {
    const editorState = stateFromText("Halló heimr villr");
    const blockKey = editorState
      .getCurrentContent()
      .getFirstBlock()
      .getKey();
    const { editorState: highlighted } = applyProofreadingResults(editorState, [
      { blockKey, result: twoResult }
    ]);
    const keys = allEntityKeys(highlighted);
    const onComplete = jest.fn();

    render(
      <ProofreadSource
        editorState={highlighted}
        entityKey={keys[0]}
        onComplete={onComplete}
      />
    );

    const applied = onComplete.mock.calls[0][0] as EditorState;
    expect(applied.getCurrentContent().getPlainText()).toBe("Halló heimur villr");
    expect(countProofreadEntities(applied)).toBe(1);
  });
});
