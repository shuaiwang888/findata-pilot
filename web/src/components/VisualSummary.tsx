import React, { useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { Alert, Card, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
// ECharts modular import: only the charts we actually render. This drops
// ~30+ unused chart types (graph, heatmap, map, sankey, tree, sunburst…)
// from the production bundle.
import * as echarts from 'echarts/core';
import { BarChart, LineChart, PieChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption as EChartsOption } from 'echarts/core';
import type { ChatResponse, JsonValue, QueryRunDetail, TablePayload, VisualChart, VisualSummary as VisualSummaryType } from '../types/api';

echarts.use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer]);

interface Props {
  response?: ChatResponse | null;
  run?: QueryRunDetail | null;
}

export function VisualSummary({ response, run }: Props) {
  const visual = response?.visual_summary || run?.visual_summary_json || null;
  const answer = response?.answer || run?.answer_text || '';
  const table = response?.table || historyTable(run);
  const question = response?.source?.query || run?.query_text || '';

  if (!visual && !answer && !table) {
    return <Alert className="inline-result-alert" type="info" message="等待查询结果" showIcon />;
  }

  if (!visual && answer && !table) {
    return null;
  }

  if (!visual) {
    if (table) {
      return (
        <ResultReport
          title="结构化数据结果"
          conclusion={answer || summarizeTable(table)}
          points={[]}
          methods={['已通过 Query2Data 返回结构化明细数据。']}
          warnings={[]}
          query={question}
          queryType="data_query"
          columns={table.columns}
          rows={table.preview}
        />
      );
    }
    return <Alert className="inline-result-alert" type="warning" message="这条记录没有保存大模型总结，请重新执行问句生成可视化结果。" showIcon />;
  }

  const columns = visual.result_columns?.length ? visual.result_columns : Object.keys(visual.result_rows?.[0] || {});
  const dataSource = visual.result_rows?.length ? visual.result_rows : table?.preview || [];
  const title = visual.title === '分析结果' || visual.query_type === 'analysis' ? '结构化结果' : visual.title || '结构化结果';

  return (
    <ResultReport
      title={title}
      conclusion={visual.headline || firstSentence(answer) || summarizeRows(dataSource)}
      points={buildPoints(visual)}
      methods={visual.method || []}
      warnings={visual.warnings || []}
      query={question}
      queryType={visual.query_type}
      columns={columns}
      rows={dataSource}
      criteria={visual.criteria}
      steps={visual.steps}
      notes={visual.notes}
      followups={visual.followups}
      chart={visual.chart ?? null}
    />
  );
}

function ResultReport({
  title,
  conclusion,
  points,
  methods,
  warnings,
  query,
  queryType,
  columns,
  rows,
  criteria,
  steps,
  notes,
  followups,
  chart
}: {
  title: string;
  conclusion: string;
  points: string[];
  methods: string[];
  warnings: string[];
  query: string;
  queryType: string;
  columns: string[];
  rows: Record<string, JsonValue>[];
  criteria?: string[];
  steps?: string[];
  notes?: string[];
  followups?: string[];
  chart?: VisualChart | null;
}) {
  const hasCriteria = (criteria?.length ?? 0) > 0;
  const hasSteps = (steps?.length ?? 0) > 0;
  const hasNotes = (notes?.length ?? 0) > 0;
  const hasFollowups = (followups?.length ?? 0) > 0;
  const hasPoints = points.length > 0;

  return (
    <Card
      className="visual-summary-card"
      title={
        <Space direction="vertical" size={2}>
          <Typography.Text strong>{title}</Typography.Text>
          <Typography.Text type="secondary">学生答卷式结构：结论 → 筛选口径 → 数据明细 → 补充说明。</Typography.Text>
        </Space>
      }
    >
      <div className="result-report">
        <ReportSection title="查询结论">
          <div className="conclusion-callout">
            <Typography.Paragraph className="summary-text">{conclusion || '本次查询已返回结构化结果，暂无额外结论。'}</Typography.Paragraph>
          </div>
        </ReportSection>

        {hasCriteria ? (
          <ReportSection title="筛选口径（我按这个逻辑跑的）">
            <BulletList items={criteria!} />
          </ReportSection>
        ) : null}

        {hasSteps ? (
          <ReportSection title="计算步骤">
            <BulletList items={steps!} />
          </ReportSection>
        ) : null}

        {hasPoints ? (
          <ReportSection title="结果要点">
            <BulletList items={points} />
          </ReportSection>
        ) : null}

        <ReportSection title="查询结果">
          <div className="data-strip">
            <span>STRUCTURED RESULT</span>
            <span>{rows.length} rows</span>
            <span>{columns.length} columns</span>
          </div>
          <StockCharts chart={chart} columns={columns} rows={rows} />
          <ResultTable columns={columns} rows={rows} />
        </ReportSection>

        {hasNotes ? (
          <ReportSection title="补充说明">
            <QuoteList items={notes!} />
          </ReportSection>
        ) : null}

        {hasFollowups ? (
          <ReportSection title="追问建议">
            <Typography.Paragraph className="followup-text">{followups!.join(' ')}</Typography.Paragraph>
          </ReportSection>
        ) : null}

        {warnings.length ? (
          <ReportSection title="注意事项">
            <BulletList items={warnings} muted />
          </ReportSection>
        ) : null}
      </div>
    </Card>
  );
}

function ReportSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="report-section">
      <Typography.Title level={4}>## {title}</Typography.Title>
      <div className="report-section-body">{children}</div>
    </section>
  );
}

function BulletList({ items, muted = false }: { items: string[]; muted?: boolean }) {
  return (
    <ul className={muted ? 'report-list muted' : 'report-list'}>
      {items.slice(0, 6).map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function QuoteList({ items }: { items: string[] }) {
  return (
    <div className="quote-block">
      {items.slice(0, 6).map((item, index) => (
        <blockquote key={`${index}-${item}`} className="note-quote">
          {item}
        </blockquote>
      ))}
    </div>
  );
}

function buildPoints(visual: VisualSummaryType) {
  const stats = (visual.stats || [])
    .slice(0, 3)
    .map((item) => `${item.label}：${item.value}${item.hint ? `（${item.hint}）` : ''}`);
  return [...stats, ...(visual.insights || [])].filter(Boolean).slice(0, 6);
}

function firstSentence(text: string) {
  return text.split(/\n|。|；|;/).map((item) => item.trim()).find(Boolean) || '';
}

function summarizeRows(rows: Record<string, JsonValue>[]) {
  return rows.length ? `本次查询返回 ${rows.length} 条结构化结果，详情见下方查询结果。` : '';
}

function summarizeTable(table: TablePayload) {
  return `本次查询返回 ${table.preview.length || table.rows} 条结构化结果，包含 ${table.columns.length} 个字段。`;
}

function StockCharts({ chart, columns, rows }: { chart?: VisualChart | null; columns: string[]; rows: Record<string, JsonValue>[] }) {
  // Memoize by the values that actually drive the chart; don't depend on
  // `columns` array identity (parent may re-create on every render) or
  // individual row data (we only need the slice that lands in the chart).
  const charts = useMemo(
    () => buildChartFromSpec(chart, columns, rows),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [chart?.type, chart?.x, chart?.y, chart?.group, rows.length]
  );
  if (!charts.length) return null;
  return (
    <div className="chart-section">
      {charts.map((item) => (
        <EChartPanel key={item.title} title={item.title} option={item.option} />
      ))}
    </div>
  );
}

const EChartPanel = React.memo(function EChartPanel({ title, option }: { title: string; option: EChartsOption }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return undefined;
    const chart = echarts.init(ref.current);
    chart.setOption(option);
    // Window-level resize only. The previous `ResizeObserver` was firing on
    // every Card-body scroll because the chart's parent participates in
    // overflow, and ECharts re-layout per tick is the second biggest
    // scroll-time cost.
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chart.dispose();
    };
  }, [option]);

  return (
    <Card size="small" title={title} className="chart-card">
      <div ref={ref} className="chart-canvas" />
    </Card>
  );
});

const ResultTable = React.memo(function ResultTable({ columns, rows }: { columns: string[]; rows: Record<string, JsonValue>[] }) {
  const tableColumns = useMemo<ColumnsType<Record<string, JsonValue>>>(() => columns.slice(0, 8).map((key) => ({
    title: key,
    dataIndex: key,
    key,
    ellipsis: true,
    render: (value: JsonValue) => String(value ?? '')
  })), [columns]);
  const dataSource = useMemo(() => rows.slice(0, 50).map((row, index) => ({ ...row, key: index })), [rows]);

  return (
    <Table
      size="small"
      columns={tableColumns}
      dataSource={dataSource}
      pagination={false}
      scroll={{ x: true, y: 420 }}
      className="result-table"
    />
  );
});

function buildChartFromSpec(
  spec: VisualChart | null | undefined,
  columns: string[],
  rows: Record<string, JsonValue>[]
): Array<{ title: string; option: EChartsOption }> {
  if (!spec || !rows.length) return [];
  const type = spec.type;
  if (type !== 'bar' && type !== 'line' && type !== 'pie') return [];

  if (type === 'pie') {
    const group = findColumn(columns, [spec.group || spec.x || '']);
    if (!group) return [];
    const counts = Array.from(
      rows.reduce((map, row) => {
        const name = shortLabel(row[group]);
        if (!name) return map;
        map.set(name, (map.get(name) || 0) + 1);
        return map;
      }, new Map<string, number>())
    )
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
    if (counts.length < 2) return [];
    return [
      {
        title: spec.reason ? `${group} 分布 · ${spec.reason}` : `${group} 分布`,
        option: {
          color: ['#2563eb', '#0891b2', '#059669', '#f59e0b', '#7c3aed', '#dc2626'],
          tooltip: { trigger: 'item' },
          legend: { bottom: 0, type: 'scroll' },
          series: [
            {
              type: 'pie',
              radius: ['42%', '68%'],
              center: ['50%', '43%'],
              data: counts,
              label: { formatter: '{b}: {d}%' }
            }
          ]
        }
      }
    ];
  }

  // bar / line both need x + y
  const xCol = findColumn(columns, [spec.x || '']);
  const yCol = findColumn(columns, [spec.y || '']);
  if (!xCol || !yCol) return [];

  const points = rows
    .map((row) => ({ name: shortLabel(row[xCol], type === 'line' ? 16 : 12), value: toNumber(row[yCol]) }))
    .filter((item) => Number.isFinite(item.value));

  if (type === 'bar') {
    const ranked = points.sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, 12);
    if (ranked.length < 2) return [];
    return [
      {
        title: spec.reason ? `${yCol} 对比 · ${spec.reason}` : `${yCol} 对比`,
        option: {
          color: ['#2563eb'],
          tooltip: { trigger: 'axis' },
          grid: { left: 42, right: 18, top: 28, bottom: 58 },
          xAxis: { type: 'category', data: ranked.map((p) => p.name), axisLabel: { rotate: 34, color: '#6b7280' } },
          yAxis: { type: 'value', axisLabel: { color: '#6b7280' }, splitLine: { lineStyle: { color: '#edf0f4' } } },
          series: [{ type: 'bar', data: ranked.map((p) => p.value), barMaxWidth: 34, itemStyle: { borderRadius: [6, 6, 0, 0] } }]
        }
      }
    ];
  }

  // line
  if (points.length < 3) return [];
  const series = points.slice(0, 60);
  return [
    {
      title: spec.reason ? `${yCol} 趋势 · ${spec.reason}` : `${yCol} 趋势`,
      option: {
        color: ['#0891b2'],
        tooltip: { trigger: 'axis' },
        grid: { left: 42, right: 18, top: 28, bottom: 42 },
        xAxis: { type: 'category', data: series.map((p) => p.name), axisLabel: { color: '#6b7280' } },
        yAxis: { type: 'value', axisLabel: { color: '#6b7280' }, splitLine: { lineStyle: { color: '#edf0f4' } } },
        series: [{ type: 'line', data: series.map((p) => p.value), smooth: true, symbolSize: 6, areaStyle: { opacity: 0.08 } }]
      }
    }
  ];
}

function findColumn(columns: string[], candidates: string[]) {
  const lowerColumns = columns.map((column) => ({ raw: column, lower: column.toLowerCase() }));
  for (const candidate of candidates) {
    const lowerCandidate = candidate.toLowerCase();
    const exact = lowerColumns.find((column) => column.lower === lowerCandidate);
    if (exact) return exact.raw;
    const partial = lowerColumns.find((column) => column.lower.includes(lowerCandidate));
    if (partial) return partial.raw;
  }
  return '';
}

function toNumber(value: JsonValue | undefined) {
  if (typeof value === 'number') return value;
  if (typeof value !== 'string') return Number.NaN;
  const cleaned = value.replace(/[%千万元亿,\s]/g, '');
  return Number(cleaned);
}

function shortLabel(value: JsonValue | undefined, max = 12) {
  const label = String(value ?? '').trim();
  return label.length > max ? `${label.slice(0, max)}...` : label;
}

function historyTable(run?: QueryRunDetail | null): TablePayload | null {
  if (!run) return null;
  const preview = (run.rows || []).map((row) => row.row_json || {});
  const first = preview[0] || {};
  const columns = Object.keys(first).length ? Object.keys(first) : (run.columns || []).map((column) => String(column.column_key || '')).filter(Boolean);
  return {
    rows: run.row_count ?? preview.length,
    columns,
    preview,
    csv_path: run.csv_path,
    parquet_path: run.parquet_path
  };
}
