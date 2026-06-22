export interface DiffAnnotation {
  orig_start_idx: number;
  orig_end_idx: number;
  orig_string: string;
  changed_start_idx: number;
  changed_end_idx: number;
  changed_string: string;
  change_type: string;
}

export interface ProofreadingResult {
  original_text: string;
  corrected_text: string;
  annotations: DiffAnnotation[];
}
