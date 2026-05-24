import { useMemo, useRef, useState } from 'react';
import { App as AntApp, Button, Layout, message, Typography } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { clearHistory, fetchHistory, fetchRun, streamChat } from './api/client';
import { ChatWorkbench } from './components/ChatWorkbench';
import { QueryRuns } from './components/QueryRuns';
import { VisualSummary } from './components/VisualSummary';
import type { ChatResponse, QueryRunDetail, StreamEvent } from './types/api';

const { Sider, Content } = Layout;

export default function App() {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('');
  const [activeRun, setActiveRun] = useState<QueryRunDetail | null>(null);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();
  const [messageApi, contextHolder] = message.useMessage();

  const historyQuery = useQuery({ queryKey: ['history'], queryFn: fetchHistory });
  const activeId = response?.source?.run_id || activeRun?.id;

  const chatMutation = useMutation({
    mutationFn: async (value: string) => {
      abortRef.current = new AbortController();
      setEvents([]);
      setActiveRun(null);
      const result = await streamChat(
        value,
        (event) => setEvents((items) => [...items, event]),
        abortRef.current.signal
      );
      return result;
    },
    onSuccess: async (result) => {
      setResponse(result);
      await queryClient.invalidateQueries({ queryKey: ['history'] });
    },
    onError: (error) => {
      if ((error as Error).name !== 'AbortError') messageApi.error((error as Error).message);
    },
    onSettled: () => {
      abortRef.current = null;
    }
  });

  const clearMutation = useMutation({
    mutationFn: clearHistory,
    onSuccess: async () => {
      setActiveRun(null);
      setResponse(null);
      await queryClient.invalidateQueries({ queryKey: ['history'] });
      messageApi.success('取数记录已清理');
    }
  });

  const selectedVisualSource = useMemo(() => ({ response, run: activeRun }), [response, activeRun]);

  async function handleSelectRun(id: number) {
    const item = await fetchRun(id);
    setActiveRun(item);
    setResponse(null);
    setEvents([]);
  }

  function handleSubmit() {
    const text = query.trim();
    if (!text) return;
    chatMutation.mutate(text);
  }

  function handleCancel() {
    abortRef.current?.abort();
  }

  function handleNewChat() {
    setResponse(null);
    setActiveRun(null);
    setEvents([]);
    setQuery('');
  }

  return (
    <AntApp>
      {contextHolder}
      <Layout className="app-shell">
        <Sider width={320} className="sidebar">
          <div className="brand">
            <div className="brand-mark">DA</div>
            <div>
              <Typography.Title level={4}>FinDataPilot</Typography.Title>
              <Typography.Text>Query2Data Intelligence Console</Typography.Text>
            </div>
          </div>
          <QueryRuns
            items={historyQuery.data || []}
            activeId={activeId || undefined}
            loading={historyQuery.isFetching}
            onSelect={handleSelectRun}
            onRefresh={() => historyQuery.refetch()}
            onClear={() => clearMutation.mutate()}
            filter={filter}
            onFilterChange={setFilter}
          />
        </Sider>
        <Layout className="content-shell">
          <div className="topbar">
            <div>
              <Typography.Text strong className="topbar-title">FinDataPilot Workbench</Typography.Text>
              <div className="topbar-subtitle">LLM Planning · Query2Data · Structured Insight</div>
            </div>
            <Button className="new-chat-btn" onClick={handleNewChat}>新建查询</Button>
          </div>
          <Content className="workspace">
            <div className="conversation-frame">
              <ChatWorkbench
                query={query}
                onQueryChange={setQuery}
                onSubmit={handleSubmit}
                onCancel={handleCancel}
                loading={chatMutation.isPending}
                response={response}
                events={events}
                run={activeRun}
              >
                <VisualSummary response={selectedVisualSource.response} run={selectedVisualSource.run} />
              </ChatWorkbench>
            </div>
          </Content>
        </Layout>
      </Layout>
    </AntApp>
  );
}
