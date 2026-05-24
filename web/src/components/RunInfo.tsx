import { Descriptions, Empty } from 'antd';
import type { ChatResponse, QueryRunDetail } from '../types/api';

interface Props {
  response?: ChatResponse | null;
  run?: QueryRunDetail | null;
}

export function RunInfo({ response, run }: Props) {
  const source = response?.source;
  const status = source
    ? source.type === 'planner'
      ? '需要补充'
      : source.status_code === 0
        ? '成功'
        : '失败'
    : run
      ? run.source === 'planner'
        ? '需要补充'
        : run.status_code === 0
          ? '成功'
          : '失败'
      : '等待查询';

  const table = response?.table;

  return (
    <div className="inspector-panel">
      <Descriptions size="small" column={1} bordered title="Run Info">
        <Descriptions.Item label="状态">{status}</Descriptions.Item>
        <Descriptions.Item label="来源">{source?.type || run?.source || '问财 query2data'}</Descriptions.Item>
        <Descriptions.Item label="Trace">{response?.trace_id || run?.trace_id || '-'}</Descriptions.Item>
        <Descriptions.Item label="任务">{source?.query || run?.query_text || '-'}</Descriptions.Item>
      </Descriptions>
      <Descriptions size="small" column={1} bordered title="Metrics" className="metrics-box">
        <Descriptions.Item label="Rows">{table?.rows ?? run?.row_count ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="Columns">{table?.columns?.length ?? run?.columns?.length ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="CSV">{table?.csv_path || run?.csv_path ? 'yes' : '-'}</Descriptions.Item>
        <Descriptions.Item label="Parquet">{table?.parquet_path || run?.parquet_path ? 'yes' : '-'}</Descriptions.Item>
      </Descriptions>
      {!response && !run ? <Empty description="查询后展示运行信息" /> : null}
    </div>
  );
}
