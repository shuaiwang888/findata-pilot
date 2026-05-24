export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface TablePayload {
  rows: number;
  columns: string[];
  preview: Record<string, JsonValue>[];
  csv_path?: string | null;
  parquet_path?: string | null;
}

export interface VisualStat {
  label: string;
  value: string;
  hint?: string;
}

export interface VisualSummary {
  title: string;
  query_type: string;
  headline: string;
  stats: VisualStat[];
  insights: string[];
  result_columns: string[];
  result_rows: Record<string, JsonValue>[];
  method: string[];
  warnings: string[];
}

export interface SourcePayload {
  type?: string;
  query?: string;
  data_query?: string;
  task_type?: string;
  analysis?: string | null;
  status_code?: number | null;
  row_count?: number | null;
  code_count?: number | null;
  run_id?: number | null;
  llm_plan?: Record<string, JsonValue>;
}

export interface ChatResponse {
  trace_id?: string | null;
  answer: string;
  visual_summary?: VisualSummary;
  table: TablePayload;
  source: SourcePayload;
  warnings: string[];
}

export interface QueryRunListItem {
  id: number;
  trace_id?: string | null;
  query_text: string;
  status_code?: number | null;
  row_count?: number | null;
  code_count?: number | null;
  source?: string | null;
  error_message?: string | null;
  csv_path?: string | null;
  parquet_path?: string | null;
  created_at?: string | null;
  answer_text?: string | null;
  visual_summary_json?: VisualSummary | null;
}

export interface QueryRunDetail extends QueryRunListItem {
  columns: Array<Record<string, JsonValue>>;
  rows: Array<{ row_order: number; row_json: Record<string, JsonValue> }>;
}

export interface StreamEvent {
  event: string;
  data: Record<string, JsonValue>;
}
