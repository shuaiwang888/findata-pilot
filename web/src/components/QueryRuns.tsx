import { Button, Input, List, Space, Tag, Typography } from 'antd';
import type { QueryRunListItem } from '../types/api';

interface Props {
  items: QueryRunListItem[];
  activeId?: number;
  loading?: boolean;
  onSelect: (id: number) => void;
  onRefresh: () => void;
  onClear: () => void;
  filter: string;
  onFilterChange: (value: string) => void;
}

export function QueryRuns(props: Props) {
  const filtered = props.items.filter((item) => {
    const text = `${item.query_text} ${item.status_code ?? ''}`.toLowerCase();
    return !props.filter || text.includes(props.filter.toLowerCase());
  });

  return (
    <div className="sidebar-panel">
      <div className="sidebar-head">
        <div>
          <Typography.Title level={5}>Query Runs</Typography.Title>
          <Typography.Text>Persisted prompts, tables and LLM summaries</Typography.Text>
        </div>
      </div>
      <Space.Compact className="search-row">
        <Input placeholder="搜索取数记录" value={props.filter} onChange={(event) => props.onFilterChange(event.target.value)} />
        <Button onClick={props.onRefresh} loading={props.loading}>刷新</Button>
        <Button onClick={props.onClear}>清理</Button>
      </Space.Compact>
      <List
        className="run-list"
        dataSource={filtered}
        locale={{ emptyText: '暂无历史记录' }}
        renderItem={(item) => (
          <List.Item
            className={props.activeId === item.id ? 'run-item active' : 'run-item'}
            onClick={() => props.onSelect(item.id)}
          >
            <div className="run-title">{item.query_text || '未命名查询'}</div>
            <div className="run-meta">
              <span>#{item.id}</span>
              <Tag color={item.answer_text ? 'cyan' : 'default'}>{item.answer_text ? 'LLM' : 'data only'}</Tag>
              <span>{item.status_code ?? '-'}</span>
              <span>{item.created_at ?? ''}</span>
            </div>
          </List.Item>
        )}
      />
    </div>
  );
}
