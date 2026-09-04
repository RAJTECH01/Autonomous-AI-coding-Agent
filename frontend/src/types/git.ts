export interface GitState {
  commit_hash: string;
  branch_name: string;
  is_dirty: boolean;
  staged_files: string[];
  unstaged_files: string[];
  untracked_files: string[];
  timestamp: string;
}

export interface FileDiffStat {
  file_path: string;
  additions: number;
  deletions: number;
  binary: boolean;
}

export interface GitDiffResult {
  diff_text: string;
  files_changed: string[];
  file_stats: FileDiffStat[];
  total_additions: number;
  total_deletions: number;
  target?: string;
  success: boolean;
  error_message?: string;
}

export interface GitCommitMetadata {
  commit_hash: string;
  branch_name: string;
  message: string;
  author_name: string;
  author_email: string;
  files_changed: string[];
  timestamp: string;
  task_id?: string;
  run_id?: string;
}

export interface GitAuditRecord {
  id: string;
  task_id: string;
  run_id?: string;
  operation: string;
  branch_name: string;
  command: string;
  exit_code: number;
  output_summary: string;
  protected_branch_checked: boolean;
  user_authorized: boolean;
  timestamp: string;
}

export interface GitPushResult {
  remote: string;
  branch_name: string;
  pushed: boolean;
  authorized: boolean;
  output: string;
  error_message?: string;
}
