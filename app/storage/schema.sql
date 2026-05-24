CREATE DATABASE IF NOT EXISTS data_agent
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE data_agent;

CREATE TABLE IF NOT EXISTS agent_query_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  trace_id CHAR(64) NOT NULL,
  query_text TEXT NOT NULL,
  page VARCHAR(32) NOT NULL DEFAULT '1',
  limit_value VARCHAR(32) NOT NULL DEFAULT '100',
  status_code INT NULL,
  row_count INT NULL,
  code_count INT NULL,
  qtime_ms INT NULL,
  token VARCHAR(128) NULL,
  source VARCHAR(64) NOT NULL DEFAULT 'iwencai_query2data',
  request_json JSON NULL,
  response_meta_json JSON NULL,
  answer_text LONGTEXT NULL,
  visual_summary_json JSON NULL,
  error_message TEXT NULL,
  csv_path TEXT NULL,
  parquet_path TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_trace_id (trace_id),
  KEY idx_created_at (created_at),
  KEY idx_status_code (status_code)
);

CREATE TABLE IF NOT EXISTS agent_query_columns (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  run_id BIGINT UNSIGNED NOT NULL,
  column_order INT NOT NULL,
  column_key VARCHAR(255) NOT NULL,
  index_name VARCHAR(255) NULL,
  fe_key VARCHAR(255) NULL,
  data_type VARCHAR(64) NULL,
  unit VARCHAR(64) NULL,
  label VARCHAR(64) NULL,
  source VARCHAR(64) NULL,
  raw_json JSON NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_run_id (run_id),
  CONSTRAINT fk_agent_query_columns_run
    FOREIGN KEY (run_id) REFERENCES agent_query_runs(id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_query_rows (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  run_id BIGINT UNSIGNED NOT NULL,
  row_order INT NOT NULL,
  row_json JSON NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_run_id (run_id),
  CONSTRAINT fk_agent_query_rows_run
    FOREIGN KEY (run_id) REFERENCES agent_query_runs(id)
    ON DELETE CASCADE
);
