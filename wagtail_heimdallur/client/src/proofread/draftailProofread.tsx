import React from "react";
import {
  ContentState,
  EditorState,
  Modifier,
  SelectionState
} from "draft-js";

import { fetchProofreadingLanguages, proofreadText } from "../api";
import type { ProofreadingResult } from "../types";
import { getDraftailLib } from "./draftailGlobals";

// Draft.js entity type used for ephemeral proofreading highlights. The entity
// carries no `icon`/`description`, so Draftail does not render a creation
// button for it — it is decoration-only. It is never persisted: a contentstate
// converter rule strips the entity (keeping its text) on save.
export const PROOFREAD_ENTITY_TYPE = "HEIMDALLUR_PROOFREAD";
export const PROOFREAD_CONTROL_TYPE = "heimdallur-proofread";
export const PROOFREAD_CLEAR_CONTROL_TYPE = "heimdallur-proofread-clear";

export interface SuggestionData {
  original: string;
  replacement: string;
  changeType: string;
}

export interface BlockSuggestion extends SuggestionData {
  start: number;
  end: number;
}

interface ProofreadableBlock {
  blockKey: string;
  text: string;
}

interface EntityRange {
  blockKey: string;
  start: number;
  end: number;
}

// ---------------------------------------------------------------------------
// Pure helpers operating on Draft.js editor state. These hold all of the
// non-trivial logic and are unit-tested directly.
// ---------------------------------------------------------------------------

export function getProofreadableBlocks(
  editorState: EditorState
): ProofreadableBlock[] {
  return editorState
    .getCurrentContent()
    .getBlocksAsArray()
    .map((block) => ({ blockKey: block.getKey(), text: block.getText() }))
    .filter((block) => block.text.trim() !== "");
}

export function buildBlockSuggestions(
  blockText: string,
  result: ProofreadingResult
): BlockSuggestion[] {
  if (result.annotations.length) {
    return result.annotations
      .map((annotation) =>
        locateSuggestion(blockText, {
          start: annotation.orig_start_idx,
          end: annotation.orig_end_idx,
          original: annotation.orig_string,
          replacement: annotation.changed_string,
          changeType: annotation.change_type
        })
      )
      .filter((suggestion): suggestion is BlockSuggestion => suggestion !== null);
  }

  if (result.corrected_text !== result.original_text) {
    return [
      {
        start: 0,
        end: blockText.length,
        original: result.original_text,
        replacement: result.corrected_text,
        changeType: "edit"
      }
    ];
  }

  return [];
}

export interface BlockProofreadingResult {
  blockKey: string;
  result: ProofreadingResult;
}

// Apply proofreading results as entities over the current editor state. Ranges
// are re-located against the *current* block text (not the text that was sent
// for proofreading) so concurrent edits during the async call cannot corrupt
// unrelated content — stale suggestions are simply skipped.
export function applyProofreadingResults(
  editorState: EditorState,
  results: BlockProofreadingResult[]
): { editorState: EditorState; applied: number } {
  let content = editorState.getCurrentContent();
  let applied = 0;

  for (const { blockKey, result } of results) {
    const block = content.getBlockForKey(blockKey);
    if (!block) {
      continue;
    }

    for (const suggestion of buildBlockSuggestions(block.getText(), result)) {
      const withEntity = content.createEntity(
        PROOFREAD_ENTITY_TYPE,
        "MUTABLE",
        {
          original: suggestion.original,
          replacement: suggestion.replacement,
          changeType: suggestion.changeType
        } satisfies SuggestionData
      );
      const entityKey = withEntity.getLastCreatedEntityKey();
      const selection = rangeSelection(blockKey, suggestion.start, suggestion.end);
      content = Modifier.applyEntity(withEntity, selection, entityKey);
      applied += 1;
    }
  }

  if (!applied) {
    return { editorState, applied };
  }

  return {
    editorState: EditorState.push(editorState, content, "apply-entity"),
    applied
  };
}

// Accept a single suggestion: replace the entity's range with its replacement
// text. The replacement carries no entity, so the highlight disappears.
export function acceptSuggestion(
  editorState: EditorState,
  entityKey: string
): EditorState {
  const content = editorState.getCurrentContent();
  const range = findEntityRange(content, entityKey);
  if (!range) {
    return editorState;
  }

  const data = content.getEntity(entityKey).getData() as SuggestionData;
  const selection = rangeSelection(range.blockKey, range.start, range.end);
  const nextContent = Modifier.replaceText(content, selection, data.replacement);
  return EditorState.push(editorState, nextContent, "insert-characters");
}

// Accept every active suggestion in a single edit: replace each highlighted
// range with its correction. Edits are applied right-to-left within each block
// so earlier replacements don't invalidate later offsets.
export function acceptAllSuggestions(editorState: EditorState): EditorState {
  const original = editorState.getCurrentContent();
  const edits: Array<{
    blockKey: string;
    start: number;
    end: number;
    replacement: string;
  }> = [];

  original.getBlocksAsArray().forEach((block) => {
    block.findEntityRanges(
      (character) => {
        const key = character.getEntity();
        return (
          key !== null &&
          original.getEntity(key).getType() === PROOFREAD_ENTITY_TYPE
        );
      },
      (start, end) => {
        const key = block.getEntityAt(start);
        if (!key) {
          return;
        }
        const data = original.getEntity(key).getData() as SuggestionData;
        edits.push({
          blockKey: block.getKey(),
          start,
          end,
          replacement: data.replacement
        });
      }
    );
  });

  if (!edits.length) {
    return editorState;
  }

  edits.sort((a, b) => b.start - a.start);
  let content = original;
  edits.forEach(({ blockKey, start, end, replacement }) => {
    const selection = rangeSelection(blockKey, start, end);
    content = Modifier.replaceText(content, selection, replacement);
  });

  return EditorState.push(editorState, content, "insert-characters");
}

// Remove every proofreading highlight, keeping the underlying text untouched.
export function removeProofreadEntities(editorState: EditorState): EditorState {
  const original = editorState.getCurrentContent();
  let content = original;
  let changed = false;

  original.getBlocksAsArray().forEach((block) => {
    const ranges: Array<[number, number]> = [];
    block.findEntityRanges(
      (character) => {
        const key = character.getEntity();
        return (
          key !== null &&
          original.getEntity(key).getType() === PROOFREAD_ENTITY_TYPE
        );
      },
      (start, end) => ranges.push([start, end])
    );

    ranges.forEach(([start, end]) => {
      const selection = rangeSelection(block.getKey(), start, end);
      content = Modifier.applyEntity(content, selection, null);
      changed = true;
    });
  });

  if (!changed) {
    return editorState;
  }

  return EditorState.push(editorState, content, "apply-entity");
}

// Number of active proofreading highlights in the current content. Recomputed
// on render so the toolbar badge tracks suggestions as they are applied,
// accepted, or dismissed.
export function countProofreadEntities(editorState: EditorState): number {
  const content = editorState.getCurrentContent();
  let count = 0;
  content.getBlocksAsArray().forEach((block) => {
    block.findEntityRanges(
      (character) => {
        const key = character.getEntity();
        return (
          key !== null &&
          content.getEntity(key).getType() === PROOFREAD_ENTITY_TYPE
        );
      },
      () => {
        count += 1;
      }
    );
  });
  return count;
}

function findEntityRange(
  content: ContentState,
  entityKey: string
): EntityRange | null {
  let found: EntityRange | null = null;

  content.getBlocksAsArray().some((block) => {
    block.findEntityRanges(
      (character) => character.getEntity() === entityKey,
      (start, end) => {
        if (!found) {
          found = { blockKey: block.getKey(), start, end };
        }
      }
    );
    return found !== null;
  });

  return found;
}

function rangeSelection(
  blockKey: string,
  start: number,
  end: number
): SelectionState {
  return SelectionState.createEmpty(blockKey).merge({
    anchorOffset: start,
    focusOffset: end
  }) as SelectionState;
}

function locateSuggestion(
  text: string,
  suggestion: BlockSuggestion
): BlockSuggestion | null {
  if (text.slice(suggestion.start, suggestion.end) === suggestion.original) {
    return suggestion;
  }

  const index = suggestion.original ? text.indexOf(suggestion.original) : -1;
  if (index < 0) {
    return null;
  }

  return {
    ...suggestion,
    start: index,
    end: index + suggestion.original.length
  };
}

export function detectLanguage(element: HTMLElement | null): string {
  const fromField = element?.closest<HTMLElement>("[lang]")?.lang;
  const documentLanguage =
    typeof document !== "undefined" ? document.documentElement.lang : "";
  return (fromField || documentLanguage || "is").split("-")[0] || "is";
}

// The language to proofread is the page's *content* locale (e.g. an Icelandic
// page being edited in an English admin), exposed by Wagtail as
// `wagtailConfig.ACTIVE_CONTENT_LOCALE`. Falls back to DOM detection when that
// is unavailable (i18n disabled, or non-page contexts).
export function detectContentLanguage(element: HTMLElement | null): string {
  const config =
    typeof window !== "undefined"
      ? (window as unknown as { wagtailConfig?: { ACTIVE_CONTENT_LOCALE?: string } })
          .wagtailConfig
      : undefined;
  const activeLocale = config?.ACTIVE_CONTENT_LOCALE;
  if (activeLocale) {
    return activeLocale.split("-")[0];
  }
  return detectLanguage(element);
}

// The set of languages a proofreading backend is configured for. Fetched once
// per page load and shared across editors; on error it resolves to an empty
// list (no language is treated as supported).
let proofreadingLanguagesPromise: Promise<string[]> | null = null;

export function loadProofreadingLanguages(): Promise<string[]> {
  if (!proofreadingLanguagesPromise) {
    proofreadingLanguagesPromise = fetchProofreadingLanguages().catch(() => []);
  }
  return proofreadingLanguagesPromise;
}

// Test seam: clears the cached lookup so each test starts fresh.
export function resetProofreadingLanguagesCache(): void {
  proofreadingLanguagesPromise = null;
}

// ---------------------------------------------------------------------------
// React components rendered by Draftail.
//
// These are class components, not function components with hooks. Wagtail's
// Draftail renders plugin components with its own React instance, which differs
// from `window.React`; React hooks require the renderer's dispatcher and so
// fail across instances, but class components are driven through the instance
// updater the renderer assigns, so they work regardless. (Draftail's own
// source/decorator examples are class components for the same reason.)
// ---------------------------------------------------------------------------

interface ControlProps {
  getEditorState: () => EditorState;
  onChange: (editorState: EditorState) => void;
}

// Icons render in a 0 0 640 640 viewBox (Font Awesome 7) and inherit the
// toolbar button colour via currentColor. Sizing/animation live in the CSS.
function SpellCheckIcon(): React.ReactElement {
  return (
    <svg
      className="heimdallur-proofread-icon"
      viewBox="0 0 640 640"
      fill="currentColor"
      aria-hidden="true"
      focusable={false}
    >
      <path d="M152 96C103.4 96 64 135.4 64 184L64 352C64 369.7 78.3 384 96 384C113.7 384 128 369.7 128 352L128 288L192 288L192 352C192 369.7 206.3 384 224 384C241.7 384 256 369.7 256 352L256 184C256 135.4 216.6 96 168 96L152 96zM192 224L128 224L128 184C128 170.7 138.7 160 152 160L168 160C181.3 160 192 170.7 192 184L192 224zM336 96C318.3 96 304 110.3 304 128L304 352C304 369.7 318.3 384 336 384L408 384C456.6 384 496 344.6 496 296C496 272.4 486.7 251 471.6 235.2C481.9 220.8 488 203.1 488 184C488 135.4 448.6 96 400 96L336 96zM400 208L368 208L368 160L400 160C413.3 160 424 170.7 424 184C424 197.3 413.3 208 400 208zM368 320L368 272L408 272C421.3 272 432 282.7 432 296C432 309.3 421.3 320 408 320L368 320zM601 404C612 390.2 609.8 370.1 596 359C582.2 347.9 562.1 350.2 551 364L445.3 496.1L406.6 457.4C394.1 444.9 373.8 444.9 361.3 457.4C348.8 469.9 348.8 490.2 361.3 502.7L425.3 566.7C431.7 573.1 440.6 576.5 449.7 576C458.8 575.5 467.2 571.1 472.9 564L601 404z" />
    </svg>
  );
}

// Same "AB" letters as the proofread icon, but with an X instead of the
// checkmark — i.e. "dismiss proofreading".
function ClearIcon(): React.ReactElement {
  return (
    <svg
      className="heimdallur-proofread-icon"
      viewBox="0 0 640 640"
      aria-hidden="true"
      focusable={false}
    >
      <path
        fill="currentColor"
        d="M152 96C103.4 96 64 135.4 64 184L64 352C64 369.7 78.3 384 96 384C113.7 384 128 369.7 128 352L128 288L192 288L192 352C192 369.7 206.3 384 224 384C241.7 384 256 369.7 256 352L256 184C256 135.4 216.6 96 168 96L152 96zM192 224L128 224L128 184C128 170.7 138.7 160 152 160L168 160C181.3 160 192 170.7 192 184L192 224z"
      />
      <path
        fill="currentColor"
        d="M336 96C318.3 96 304 110.3 304 128L304 352C304 369.7 318.3 384 336 384L408 384C456.6 384 496 344.6 496 296C496 272.4 486.7 251 471.6 235.2C481.9 220.8 488 203.1 488 184C488 135.4 448.6 96 400 96L336 96zM400 208L368 208L368 160L400 160C413.3 160 424 170.7 424 184C424 197.3 413.3 208 400 208zM368 320L368 272L408 272C421.3 272 432 282.7 432 296C432 309.3 421.3 320 408 320L368 320z"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth={64}
        strokeLinecap="round"
        d="M404 412 L556 564"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth={64}
        strokeLinecap="round"
        d="M556 412 L404 564"
      />
    </svg>
  );
}

function SpinnerIcon(): React.ReactElement {
  return (
    <svg
      className="heimdallur-proofread-icon heimdallur-proofread-icon--spin"
      viewBox="0 0 640 640"
      fill="none"
      stroke="currentColor"
      strokeWidth={72}
      strokeLinecap="round"
      aria-hidden="true"
      focusable={false}
    >
      <path d="M320 96 A224 224 0 1 1 144 184" />
    </svg>
  );
}

// Double checkmark — "apply all suggestions".
function ApplyAllIcon(): React.ReactElement {
  return (
    <svg
      className="heimdallur-proofread-icon"
      viewBox="0 0 640 640"
      fill="none"
      stroke="currentColor"
      strokeWidth={60}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable={false}
    >
      <path d="M72 332 L200 460 L392 236" />
      <path d="M248 332 L376 460 L568 236" />
    </svg>
  );
}

// Single checkmark — "accept this suggestion".
function CheckIcon(): React.ReactElement {
  return (
    <svg
      className="heimdallur-proofread-icon"
      viewBox="0 0 640 640"
      fill="none"
      stroke="currentColor"
      strokeWidth={64}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable={false}
    >
      <path d="M132 340 L256 464 L508 200" />
    </svg>
  );
}

// Plain X — "dismiss this suggestion".
function CrossIcon(): React.ReactElement {
  return (
    <svg
      className="heimdallur-proofread-icon"
      viewBox="0 0 640 640"
      fill="none"
      stroke="currentColor"
      strokeWidth={64}
      strokeLinecap="round"
      aria-hidden="true"
      focusable={false}
    >
      <path d="M180 180 L460 460" />
      <path d="M460 180 L180 460" />
    </svg>
  );
}

function ToolbarButton(props: {
  name: string;
  title: string;
  icon: React.ReactNode;
  active?: boolean;
  onClick: () => void;
}): React.ReactElement {
  // Draftail renders `label` (any node) inside the button and uses `title`
  // as both the balloon tooltip and the accessible name, so the SVG goes in
  // `label` and `title` carries the stable accessible label.
  const Button = getDraftailLib().ToolbarButton as
    | React.ComponentType<{
        name: string;
        title: string;
        label: React.ReactNode;
        active?: boolean;
        onClick: () => void;
      }>
    | undefined;
  if (Button) {
    return (
      <Button
        name={props.name}
        title={props.title}
        label={props.icon}
        active={props.active}
        onClick={props.onClick}
      />
    );
  }

  return (
    <button
      type="button"
      name={props.name}
      className="Draftail-ToolbarButton"
      aria-label={props.title}
      title={props.title}
      onMouseDown={(event) => event.preventDefault()}
      onClick={props.onClick}
    >
      {props.icon}
    </button>
  );
}

interface ProofreadControlState {
  busy: boolean;
  status: string;
  // null while the supported languages are still loading.
  languages: string[] | null;
}

export class ProofreadControl extends React.Component<
  ControlProps,
  ProofreadControlState
> {
  state: ProofreadControlState = { busy: false, status: "", languages: null };
  private group: HTMLDivElement | null = null;
  private mounted = false;

  componentDidMount(): void {
    this.mounted = true;
    loadProofreadingLanguages().then((languages) => {
      if (this.mounted) {
        this.setState({ languages });
      }
    });
  }

  componentWillUnmount(): void {
    this.mounted = false;
  }

  private run = async (): Promise<void> => {
    if (this.state.busy) {
      return;
    }

    const { getEditorState, onChange } = this.props;
    const blocks = getProofreadableBlocks(getEditorState());
    if (!blocks.length) {
      this.setState({ status: "No text to proofread." });
      return;
    }

    this.setState({ busy: true, status: "" });
    try {
      const language = detectContentLanguage(this.group);
      const results = await Promise.all(
        blocks.map(async (block) => ({
          blockKey: block.blockKey,
          result: await proofreadText(block.text, language)
        }))
      );
      const { editorState: next, applied } = applyProofreadingResults(
        getEditorState(),
        results
      );
      if (applied) {
        // The count badge conveys the result; clear any prior message.
        onChange(next);
        this.setState({ status: "" });
      } else {
        this.setState({ status: "No proofreading suggestions." });
      }
    } catch (error) {
      this.setState({
        status: error instanceof Error ? error.message : "Proofreading failed."
      });
    } finally {
      this.setState({ busy: false });
    }
  };

  private applyAll = (): void => {
    const { getEditorState, onChange } = this.props;
    const next = acceptAllSuggestions(getEditorState());
    if (next !== getEditorState()) {
      onChange(next);
    }
  };

  render(): React.ReactElement | null {
    const { busy, status, languages } = this.state;

    // Hide the control when a proofreading backend is configured but none
    // supports this page's content language (e.g. Málstaður only proofreads
    // Icelandic). While the supported set is still loading the button shows
    // optimistically, so it doesn't pop in on the common (supported) case.
    if (
      languages !== null &&
      !languages.includes(detectContentLanguage(this.group))
    ) {
      return null;
    }

    const count = countProofreadEntities(this.props.getEditorState());

    // Once suggestions exist, the button becomes "apply all"; while idle it
    // (re)runs proofreading.
    let icon: React.ReactNode;
    let title: string;
    let onClick: () => void;
    if (busy) {
      icon = <SpinnerIcon />;
      title = "Proofreading…";
      onClick = this.run;
    } else if (count > 0) {
      icon = <ApplyAllIcon />;
      title = "Apply all suggestions";
      onClick = this.applyAll;
    } else {
      icon = <SpellCheckIcon />;
      title = "Proofread";
      onClick = this.run;
    }

    return (
      <div
        ref={(element) => {
          this.group = element;
        }}
        className="Draftail-ToolbarGroup heimdallur-proofread-toolbar"
      >
        <span className="heimdallur-proofread-button">
          <ToolbarButton
            name={PROOFREAD_CONTROL_TYPE}
            title={title}
            icon={icon}
            onClick={onClick}
          />
          {count > 0 ? (
            <span className="heimdallur-proofread-badge" aria-hidden="true">
              {count}
            </span>
          ) : null}
        </span>
        {status ? (
          <span className="heimdallur-proofread-status" role="status">
            {status}
          </span>
        ) : null}
      </div>
    );
  }
}

export class ClearProofreadingControl extends React.Component<ControlProps> {
  private clear = (): void => {
    const { getEditorState, onChange } = this.props;
    const next = removeProofreadEntities(getEditorState());
    if (next !== getEditorState()) {
      onChange(next);
    }
  };

  render(): React.ReactElement | null {
    // Only offer "dismiss" once a proofreading run has produced suggestions.
    if (countProofreadEntities(this.props.getEditorState()) === 0) {
      return null;
    }
    return (
      <ToolbarButton
        name={PROOFREAD_CLEAR_CONTROL_TYPE}
        title="Dismiss all proofreading suggestions"
        icon={<ClearIcon />}
        onClick={this.clear}
      />
    );
  }
}

// "Accept all" from a suggestion popover routes through Draftail's per-entity
// `onEdit` (the only editor-bound hook a decorator has). This one-shot flag,
// set immediately before `onEdit` and consumed synchronously when the source
// mounts, tells the source to apply every suggestion instead of just this one —
// so it can't leak across editors.
let pendingApplyAll = false;

function requestApplyAll(): void {
  pendingApplyAll = true;
}

function consumePendingApplyAll(): boolean {
  const value = pendingApplyAll;
  pendingApplyAll = false;
  return value;
}

interface PopoverHandle {
  close: () => void;
  contains: (target: Node | null) => boolean;
}

// Keeps at most one suggestion popover open and closes it on an outside click.
const popoverManager = {
  active: null as PopoverHandle | null,
  open(handle: PopoverHandle): void {
    if (this.active && this.active !== handle) {
      this.active.close();
    }
    this.active = handle;
    document.addEventListener("mousedown", this.onDocumentMouseDown, true);
  },
  close(handle: PopoverHandle): void {
    if (this.active === handle) {
      this.active = null;
      document.removeEventListener("mousedown", this.onDocumentMouseDown, true);
    }
  },
  onDocumentMouseDown(event: MouseEvent): void {
    const active = popoverManager.active;
    if (active && !active.contains(event.target as Node)) {
      active.close();
    }
  }
};

interface DecoratorProps {
  contentState: ContentState;
  entityKey: string;
  children: React.ReactNode;
  onEdit: (entityKey: string) => void;
  onRemove: (entityKey: string) => void;
}

interface DecoratorState {
  open: boolean;
  top: number;
  left: number;
}

export class SuggestionDecorator extends React.Component<
  DecoratorProps,
  DecoratorState
> {
  state: DecoratorState = { open: false, top: 0, left: 0 };
  private anchor: HTMLElement | null = null;
  private popover: HTMLElement | null = null;
  private handle: PopoverHandle = {
    close: () => this.close(),
    contains: (target) =>
      !!target &&
      (!!this.popover?.contains(target) || !!this.anchor?.contains(target))
  };

  componentWillUnmount(): void {
    this.unbind();
    popoverManager.close(this.handle);
  }

  // The popover is `position: fixed` so it escapes the editor's
  // `overflow: auto`/`hidden` ancestors and their low stacking contexts (there
  // are no transformed ancestors, so fixed is anchored to the viewport). It is
  // closed on scroll/resize since its coordinates are captured on open.
  private bind(): void {
    window.addEventListener("scroll", this.close, true);
    window.addEventListener("resize", this.close);
  }

  private unbind(): void {
    window.removeEventListener("scroll", this.close, true);
    window.removeEventListener("resize", this.close);
  }

  private toggle = (): void => {
    if (this.state.open) {
      this.close();
      return;
    }
    const rect = this.anchor?.getBoundingClientRect();
    this.bind();
    popoverManager.open(this.handle);
    this.setState({
      open: true,
      top: rect ? rect.bottom + 4 : 0,
      left: rect ? rect.left : 0
    });
  };

  private close = (): void => {
    if (!this.state.open) {
      return;
    }
    this.unbind();
    popoverManager.close(this.handle);
    this.setState({ open: false });
  };

  private acceptAll = (): void => {
    this.close();
    requestApplyAll();
    this.props.onEdit(this.props.entityKey);
  };

  private accept = (): void => {
    this.close();
    this.props.onEdit(this.props.entityKey);
  };

  private dismiss = (): void => {
    this.close();
    this.props.onRemove(this.props.entityKey);
  };

  render(): React.ReactElement {
    const { contentState, entityKey, children } = this.props;
    const data = contentState.getEntity(entityKey).getData() as SuggestionData;

    return (
      <span className="heimdallur-proofread-suggestion">
        <span
          ref={(element) => {
            this.anchor = element;
          }}
          role="button"
          tabIndex={0}
          className="heimdallur-proofread-suggestion__text"
          title={`${data.original} → ${data.replacement}`}
          onMouseDown={(event) => event.preventDefault()}
          onClick={this.toggle}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              this.toggle();
            }
          }}
        >
          {children}
        </span>
        {this.state.open ? (
          <span
            ref={(element) => {
              this.popover = element;
            }}
            className="heimdallur-proofread-popover"
            role="dialog"
            aria-label="Proofreading suggestion"
            contentEditable={false}
            style={{ top: this.state.top, left: this.state.left }}
          >
            <span className="heimdallur-proofread-popover__diff">
              <del className="heimdallur-proofread-popover__original">
                {data.original}
              </del>
              <span
                className="heimdallur-proofread-popover__arrow"
                aria-hidden="true"
              >
                →
              </span>
              <span className="heimdallur-proofread-popover__suggestion">
                {data.replacement}
              </span>
            </span>
            <span className="heimdallur-proofread-popover__actions">
              <button
                type="button"
                className="heimdallur-proofread-action"
                title="Accept all suggestions"
                aria-label="Accept all suggestions"
                onMouseDown={(event) => event.preventDefault()}
                onClick={this.acceptAll}
              >
                <ApplyAllIcon />
              </button>
              <span className="heimdallur-proofread-popover__actions-group">
                <button
                  type="button"
                  className="heimdallur-proofread-action"
                  title="Accept"
                  aria-label="Accept suggestion"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={this.accept}
                >
                  <CheckIcon />
                </button>
                <button
                  type="button"
                  className="heimdallur-proofread-action heimdallur-proofread-action--dismiss"
                  title="Dismiss"
                  aria-label="Dismiss suggestion"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={this.dismiss}
                >
                  <CrossIcon />
                </button>
              </span>
            </span>
          </span>
        ) : null}
      </span>
    );
  }
}

interface SourceProps {
  editorState: EditorState;
  entityKey: string;
  onComplete: (editorState: EditorState) => void;
}

// Headless "source" triggered by Draftail when the user clicks Accept or
// Accept all (`onEdit`). It applies the correction(s) and completes immediately.
export class ProofreadSource extends React.Component<SourceProps> {
  componentDidMount(): void {
    const { editorState, entityKey, onComplete } = this.props;
    onComplete(
      consumePendingApplyAll()
        ? acceptAllSuggestions(editorState)
        : acceptSuggestion(editorState, entityKey)
    );
  }

  render(): null {
    return null;
  }
}
