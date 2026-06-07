import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { Button, Collapse, Input, Progress, Space, Tag, Typography } from 'antd';
import type { ChatResponse, QueryRunDetail, StreamEvent } from '../types/api';
import { Typewriter } from './Typewriter';

interface Props {
  query: string;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  loading: boolean;
  response?: ChatResponse | null;
  events: StreamEvent[];
  run?: QueryRunDetail | null;
  children?: ReactNode;
}

export function ChatWorkbench(props: Props) {
  const progress = latestProgress(props.events);
  const plan = latestPlan(props.events);
  const activeQuestion = props.response?.source?.query || props.run?.query_text || '';
  const answer = props.response?.answer || props.run?.answer_text || '';
  const hasResultSource = Boolean(props.response || props.run);
  const hasConversation = Boolean(activeQuestion || props.loading || answer || hasResultSource);
  const traceItems = props.events.slice(-8);

  // Build the streaming answer: concat all summary_delta chunks received so far.
  // If the stream has finished, the final `answer` from the response wins.
  const streamingAnswer = useMemo(() => buildStreamingAnswer(props.events), [props.events]);
  const isStreamingSummary = props.loading && streamingAnswer.length > 0;
  const displayAnswer = isStreamingSummary ? streamingAnswer : answer;

  return (
    <section className="chat-card">
      <div className="chat-content">
        {!hasConversation ? (
          <div className="empty-state">
            <div className="empty-kicker">DATA AGENT</div>
            <Typography.Title level={2}>问数据，拿结构化答案</Typography.Title>
            <Typography.Text>
              输入选股、行情、持仓或经营指标问题，系统会先拆解意图，再调用 Query2Data 取数并生成可视化总结。
            </Typography.Text>
          </div>
        ) : null}

        {activeQuestion ? (
          <div className="message-row user">
            <div className="message-bubble user-bubble">{activeQuestion}</div>
          </div>
        ) : null}

        {(props.loading || traceItems.length || plan?.steps?.length) ? (
          <div className="message-row assistant">
            <div className="assistant-avatar">DA</div>
            <div className="assistant-message">
              <div className="assistant-meta">
                <span>执行规划</span>
                <Tag color={props.loading ? 'processing' : 'default'}>{props.loading ? '运行中' : '已完成'}</Tag>
              </div>
              <Progress percent={progress} size="small" showInfo={false} />
              <Collapse
                ghost
                className="trace-collapse"
                items={[
                  {
                    key: 'trace',
                    label: `查看步骤${plan?.steps?.length ? ` (${plan.steps.length})` : ''}`,
                    children: (
                      <div className="plan-steps">
                        {plan?.steps?.length
                          ? plan.steps.map((step: unknown, index: number) => (
                              <div key={`${index}-${String(step)}`} className="plan-step">
                                <span>{index + 1}</span>
                                <Typography.Text>{String(step)}</Typography.Text>
                              </div>
                            ))
                          : traceItems.map((item, index) => (
                              <div key={`${index}-${item.event}`} className="plan-step">
                                <span>{index + 1}</span>
                                <Typography.Text type="secondary">{String(item.data.message || item.event)}</Typography.Text>
                              </div>
                            ))}
                      </div>
                    )
                  }
                ]}
              />
            </div>
          </div>
        ) : null}

        {(displayAnswer || hasResultSource) ? (
          <div className="message-row assistant">
            <div className="assistant-avatar">{isStreamingSummary ? '··' : 'AI'}</div>
            <div className="assistant-message result-message">
              {displayAnswer && !hasResultSource ? (
                <Typewriter
                  text={displayAnswer}
                  streaming={isStreamingSummary}
                />
              ) : null}
              {hasResultSource ? props.children : null}
            </div>
          </div>
        ) : null}
      </div>
      <Space.Compact className="composer-row">
        <Input.TextArea
          value={props.query}
          onChange={(event) => props.onQueryChange(event.target.value)}
          placeholder="例如：我的自选股涨跌幅情况"
          autoSize={{ minRows: 2, maxRows: 5 }}
          disabled={props.loading}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              props.onSubmit();
            }
          }}
        />
        <Button type="primary" onClick={props.onSubmit} loading={props.loading}>发送</Button>
        {props.loading ? <Button onClick={props.onCancel}>取消</Button> : null}
      </Space.Compact>
    </section>
  );
}

function latestProgress(events: StreamEvent[]): number {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const progress = Number(events[index].data.progress || 0);
    if (progress) return progress;
  }
  return events.length ? 10 : 0;
}

function latestPlan(events: StreamEvent[]): { steps?: unknown[] } | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const plan = events[index].data.plan;
    if (plan && typeof plan === 'object' && !Array.isArray(plan)) return plan as { steps?: unknown[] };
  }
  return null;
}

function buildStreamingAnswer(events: StreamEvent[]): string {
  let acc = '';
  for (const event of events) {
    if (event.event === 'summary_delta') {
      const delta = event.data.delta;
      if (typeof delta === 'string' && delta) acc += delta;
    }
  }
  return acc;
}
