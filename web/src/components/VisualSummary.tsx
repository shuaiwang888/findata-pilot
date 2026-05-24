import { useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { Alert, Card, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import type { ChatResponse, JsonValue, QueryRunDetail, SourcePayload, TablePayload, VisualSummary as VisualSummaryType } from '../types/api';

type SourceInfo = SourcePayload | QueryRunDetail | null;

interface Props {
  response?: ChatResponse | null;
  run?: QueryRunDetail | null;
}

export function VisualSummary({ response, run }: Props) {
  const visual = response?.visual_summary || run?.visual_summary_json || null;
  const answer = response?.answer || run?.answer_text || '';
  const table = response?.table || historyTable(run);
  const question = response?.source?.query || run?.query_text || '';
  const source = response?.source || run || null;

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
          source={source}
          table={table}
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
      source={source}
      table={table}
      query={question}
      queryType={visual.query_type}
      columns={columns}
      rows={dataSource}
    />
  );
}

function ResultReport({
  title,
  conclusion,
  points,
  methods,
  warnings,
  source,
  table,
  query,
  queryType,
  columns,
  rows
}: {
  title: string;
  conclusion: string;
  points: string[];
  methods: string[];
  warnings: string[];
  source: SourceInfo;
  table?: TablePayload | null;
  query: string;
  queryType: string;
  columns: string[];
  rows: Record<string, JsonValue>[];
}) {
  return (
    <Card
      className="visual-summary-card"
      title={
        <Space direction="vertical" size={2}>
          <Typography.Text strong>{title}</Typography.Text>
          <Typography.Text type="secondary">查询结果已按结论、要点、口径、可视化和数据来源汇总。</Typography.Text>
        </Space>
      }
    >
      <div className="result-report">
        <ReportSection title="查询结论">
          <Typography.Paragraph className="summary-text">{conclusion || '本次查询已返回结构化结果，暂无额外结论。'}</Typography.Paragraph>
        </ReportSection>

        <ReportSection title="结果要点">
          {points.length ? <BulletList items={points} /> : <Typography.Text type="secondary">暂无可提炼的结果要点。</Typography.Text>}
        </ReportSection>

        <ReportSection title="口径与处理">
          {methods.length ? <BulletList items={methods} /> : <Typography.Text type="secondary">按 Query2Data 返回字段直接展示，未追加额外处理口径。</Typography.Text>}
        </ReportSection>

        <ReportSection title="查询结果">
          <div className="data-strip">
            <span>STRUCTURED RESULT</span>
            <span>{rows.length} rows</span>
            <span>{columns.length} columns</span>
          </div>
          <StockCharts query={query} queryType={queryType} columns={columns} rows={rows} />
          <ResultTable columns={columns} rows={rows} />
        </ReportSection>

        <ReportSection title="数据来源">
          <SourceBlock source={source} table={table} />
        </ReportSection>

        <ReportSection title="注意事项">
          {warnings.length ? <BulletList items={warnings} muted /> : <Typography.Text type="secondary">结果基于当前接口返回数据生成，请结合数据时间和业务口径复核。</Typography.Text>}
        </ReportSection>
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

function SourceBlock({ source, table }: { source: SourceInfo; table?: TablePayload | null }) {
  const items = [
    sourceValue('来源', getSourceField(source, 'type') || getSourceField(source, 'source')),
    sourceValue('状态', source?.status_code),
    sourceValue('行数', source?.row_count || table?.rows),
    sourceValue('字段数', table?.columns?.length),
    sourceValue('CSV', table?.csv_path),
    sourceValue('Parquet', table?.parquet_path)
  ].filter((item): item is { label: string; value: string } => Boolean(item));

  if (!items.length) return <Typography.Text type="secondary">暂无明确数据来源信息。</Typography.Text>;

  return (
    <div className="source-grid">
      {items.map((item) => (
        <div key={item.label} className="source-item">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

function getSourceField(source: SourceInfo, key: 'type' | 'source') {
  if (!source || !(key in source)) return undefined;
  return (source as Record<string, unknown>)[key];
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

function sourceValue(label: string, value: unknown) {
  if (value === undefined || value === null || value === '') return null;
  return { label, value: String(value) };
}

function StockCharts({ query, queryType, columns, rows }: { query: string; queryType: string; columns: string[]; rows: Record<string, JsonValue>[] }) {
  const charts = useMemo(() => buildStockCharts(query, queryType, columns, rows), [query, queryType, columns, rows]);
  if (!charts.length) return null;
  return (
    <div className="chart-section">
      {charts.map((chart) => (
        <EChartPanel key={chart.title} title={chart.title} option={chart.option} />
      ))}
    </div>
  );
}

function EChartPanel({ title, option }: { title: string; option: EChartsOption }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return undefined;
    const chart = echarts.init(ref.current);
    chart.setOption(option);
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    const observer = new ResizeObserver(resize);
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', resize);
      chart.dispose();
    };
  }, [option]);

  return (
    <Card size="small" title={title} className="chart-card">
      <div ref={ref} className="chart-canvas" />
    </Card>
  );
}

function ResultTable({ columns, rows }: { columns: string[]; rows: Record<string, JsonValue>[] }) {
  const tableColumns: ColumnsType<Record<string, JsonValue>> = columns.slice(0, 8).map((key) => ({
    title: key,
    dataIndex: key,
    key,
    ellipsis: true,
    render: (value) => String(value ?? '')
  }));

  return (
    <Table
      size="small"
      columns={tableColumns}
      dataSource={rows.slice(0, 50).map((row, index) => ({ ...row, key: index }))}
      pagination={false}
      scroll={{ x: true, y: 420 }}
      className="result-table"
    />
  );
}

function buildStockCharts(query: string, queryType: string, columns: string[], rows: Record<string, JsonValue>[]) {
  if (!rows.length || !isStockQuery(query, queryType, columns)) return [];

  const labelKey = findColumn(columns, ['股票名称', '证券简称', '名称', 'name', '股票代码', '证券代码', '代码', 'symbol', 'code']);
  const dateKey = findColumn(columns, ['交易日期', '日期', '时间', 'date', 'datetime', 'trade_date']);
  const pctKey = findColumn(columns, ['涨跌幅', '涨幅', '跌幅', '收益率', 'return', 'pct_chg', 'change_pct']);
  const priceKey = findColumn(columns, ['收盘价', '最新价', '现价', '价格', 'close', 'price', 'last']);
  const amountKey = findColumn(columns, ['成交额', '成交金额', '市值', '总市值', '流通市值', 'amount', 'market_cap']);
  const volumeKey = findColumn(columns, ['成交量', 'volume', 'vol']);
  const industryKey = findColumn(columns, ['行业', '所属行业', '板块', '概念', 'industry', 'sector']);
  const numericKey = pctKey || priceKey || amountKey || volumeKey || findNumericColumn(columns, rows);
  const label = labelKey || dateKey || columns[0];

  const charts: Array<{ title: string; option: EChartsOption }> = [];

  if (numericKey && label) {
    const rankedRows = rows
      .map((row) => ({ name: shortLabel(row[label]), value: toNumber(row[numericKey]) }))
      .filter((item) => Number.isFinite(item.value))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, 12);

    if (rankedRows.length >= 2) {
      charts.push({
        title: pctKey ? '涨跌幅对比' : `${numericKey} 对比`,
        option: {
          color: ['#2563eb'],
          tooltip: { trigger: 'axis' },
          grid: { left: 42, right: 18, top: 28, bottom: 58 },
          xAxis: { type: 'category', data: rankedRows.map((item) => item.name), axisLabel: { rotate: 34, color: '#6b7280' } },
          yAxis: { type: 'value', axisLabel: { color: '#6b7280' }, splitLine: { lineStyle: { color: '#edf0f4' } } },
          series: [{ type: 'bar', data: rankedRows.map((item) => item.value), barMaxWidth: 34, itemStyle: { borderRadius: [6, 6, 0, 0] } }]
        }
      });
    }
  }

  if (dateKey && numericKey) {
    const lineRows = rows
      .map((row) => ({ name: shortLabel(row[dateKey], 16), value: toNumber(row[numericKey]) }))
      .filter((item) => Number.isFinite(item.value))
      .slice(0, 60);

    if (lineRows.length >= 3) {
      charts.push({
        title: `${numericKey} 趋势`,
        option: {
          color: ['#0891b2'],
          tooltip: { trigger: 'axis' },
          grid: { left: 42, right: 18, top: 28, bottom: 42 },
          xAxis: { type: 'category', data: lineRows.map((item) => item.name), axisLabel: { color: '#6b7280' } },
          yAxis: { type: 'value', axisLabel: { color: '#6b7280' }, splitLine: { lineStyle: { color: '#edf0f4' } } },
          series: [{ type: 'line', data: lineRows.map((item) => item.value), smooth: true, symbolSize: 6, areaStyle: { opacity: 0.08 } }]
        }
      });
    }
  }

  if (industryKey) {
    const industryRows = Array.from(
      rows.reduce((map, row) => {
        const name = shortLabel(row[industryKey]);
        if (!name) return map;
        map.set(name, (map.get(name) || 0) + 1);
        return map;
      }, new Map<string, number>())
    )
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);

    if (industryRows.length >= 2) {
      charts.push({
        title: '行业分布',
        option: {
          color: ['#2563eb', '#0891b2', '#059669', '#f59e0b', '#7c3aed', '#dc2626'],
          tooltip: { trigger: 'item' },
          legend: { bottom: 0, type: 'scroll' },
          series: [
            {
              type: 'pie',
              radius: ['42%', '68%'],
              center: ['50%', '43%'],
              data: industryRows,
              label: { formatter: '{b}: {d}%' }
            }
          ]
        }
      });
    }
  }

  return charts.slice(0, 3);
}

function isStockQuery(query: string, queryType: string, columns: string[]) {
  const text = `${query} ${queryType} ${columns.join(' ')}`.toLowerCase();
  return /选股|股票|证券|个股|自选股|涨跌幅|收盘价|成交额|成交量|市值|行业|板块|stock|symbol|ticker|pct_chg|close/.test(text);
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

function findNumericColumn(columns: string[], rows: Record<string, JsonValue>[]) {
  return columns.find((column) => rows.some((row) => Number.isFinite(toNumber(row[column])))) || '';
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
