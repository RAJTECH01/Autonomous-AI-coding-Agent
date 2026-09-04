export interface ProjectFile {
  id: string;
  file_path: string;
  size_bytes: number;
  last_modified: string;
  content?: string;
  is_directory?: boolean;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string;
  language: string;
  framework: string;
  created_at: string;
  updated_at: string;
  files_count: number;
  tasks_count: number;
}
