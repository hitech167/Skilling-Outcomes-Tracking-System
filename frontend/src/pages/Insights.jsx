import { useEffect, useState } from 'react';
import {
  Card,
  Spin,
  Typography,
  Row,
  Col,
  Table,
  Tabs,
  Progress,
  Alert,
  Empty,
  Tag,
  List,
} from 'antd';
import {
  BulbOutlined,
  ToolOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const { Title, Text } = Typography;

// Several /api/insights endpoints are subsets of these (skill-gaps,
// additional-training, additional-training/by-course, programme-improvement),
// so only the ones that carry distinct data are fetched.
const ENDPOINTS = {
  summary: '/api/insights/summary',
  remedial: '/api/insights/remedial-actions',
  accountability: '/api/insights/accountability',
  courseGaps: '/api/insights/skill-gaps/by-course',
  districts: '/api/insights/resource-allocation',
  nonPlacement: '/api/insights/non-placement',
  attrition: '/api/insights/attrition',
  relevance: '/api/insights/training-relevance',
  longitudinal: '/api/insights/longitudinal-outcomes',
  dataQuality: '/api/insights/data-quality',
};

const METRIC_LABELS = {
  skill_gap_percentage: 'Skill gap',
  average_training_relevance: 'Avg. relevance',
  location_problem_percentage: 'Location barriers',
  retention_rate: 'Retention rate',
};

const DATA_QUALITY_GROUPS = [
  {
    title: 'Outcome tracking gaps',
    highlight: true,
    items: [
      { key: 'completed_training_without_outcome', label: 'Completed trainings without an outcome' },
      { key: 'employment_without_wage_history', label: 'Employments without wage history' },
      { key: 'employment_without_verification', label: 'Employments without verification' },
      { key: 'employment_without_status_history', label: 'Employments without status history' },
    ],
  },
  {
    title: 'Trainee records',
    items: [
      { key: 'trainees_missing_phone', label: 'Missing phone' },
      { key: 'trainees_missing_location', label: 'Missing location' },
      { key: 'trainees_missing_gender', label: 'Missing gender' },
      { key: 'trainees_missing_dob', label: 'Missing date of birth' },
      { key: 'possible_duplicate_trainees', label: 'Possible duplicate trainees' },
    ],
  },
  {
    title: 'Training records',
    items: [
      { key: 'training_missing_completion_date', label: 'Missing completion date' },
      { key: 'training_missing_attendance', label: 'Missing attendance' },
      { key: 'training_missing_assessment', label: 'Missing assessment' },
    ],
  },
  {
    title: 'Employment & follow-ups',
    items: [
      { key: 'employment_missing_salary', label: 'Employments missing salary' },
      { key: 'employment_missing_joining_date', label: 'Employments missing joining date' },
      { key: 'followups_not_completed', label: 'Follow-ups not completed' },
      { key: 'followups_not_reachable', label: 'Follow-ups not reachable' },
    ],
  },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: 'easeOut' },
  },
};

const cardStyle = {
  borderRadius: 12,
  border: '1px solid #eef0f3',
  boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
};

function pct(value) {
  return value === null || value === undefined ? '—' : `${Number(value).toFixed(1)}%`;
}

function rating(value) {
  return value === null || value === undefined ? '—' : `${Number(value).toFixed(1)} / 5`;
}

function formatMetric(key, value) {
  return key === 'average_training_relevance' ? rating(value) : pct(value);
}

function PercentBar({ value, danger }) {
  return (
    <Progress
      percent={value}
      size="small"
      status={danger ? 'exception' : 'normal'}
      format={(p) => `${p.toFixed(1)}%`}
      style={{ minWidth: 120 }}
    />
  );
}

function SectionError({ error }) {
  return <Alert type="error" showIcon message={error} />;
}

function Stat({ label, value }) {
  return (
    <Card style={{ ...cardStyle, height: '100%' }} styles={{ body: { padding: 20 } }}>
      <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>
        {label}
      </Text>
      <div style={{ fontSize: 26, fontWeight: 600, color: '#1f2937', marginTop: 4 }}>{value}</div>
    </Card>
  );
}

function accountabilityColumns(nameTitle) {
  return [
    {
      title: nameTitle,
      dataIndex: 'name',
      key: 'name',
      sorter: (a, b) => a.name.localeCompare(b.name),
    },
    {
      title: 'Trainees',
      dataIndex: 'total_trainees',
      key: 'total_trainees',
      align: 'right',
      sorter: (a, b) => a.total_trainees - b.total_trainees,
    },
    {
      title: 'Completion',
      dataIndex: 'completion_rate',
      key: 'completion_rate',
      render: pct,
      sorter: (a, b) => a.completion_rate - b.completion_rate,
    },
    {
      title: 'Placement',
      dataIndex: 'placement_rate',
      key: 'placement_rate',
      render: pct,
      sorter: (a, b) => a.placement_rate - b.placement_rate,
    },
    {
      title: 'Employment',
      dataIndex: 'employment_rate',
      key: 'employment_rate',
      render: pct,
      sorter: (a, b) => a.employment_rate - b.employment_rate,
    },
    {
      title: 'Retention',
      dataIndex: 'retention_rate',
      key: 'retention_rate',
      render: pct,
      sorter: (a, b) => a.retention_rate - b.retention_rate,
    },
    {
      title: 'Skill gap',
      dataIndex: 'skill_gap_percentage',
      key: 'skill_gap_percentage',
      render: pct,
      sorter: (a, b) => a.skill_gap_percentage - b.skill_gap_percentage,
    },
    {
      title: 'Attrition',
      dataIndex: 'attrition_rate',
      key: 'attrition_rate',
      render: pct,
      sorter: (a, b) => a.attrition_rate - b.attrition_rate,
    },
    {
      title: 'Relevance',
      dataIndex: 'average_training_relevance',
      key: 'average_training_relevance',
      render: rating,
    },
    {
      title: 'Salary growth',
      dataIndex: 'average_salary_growth_percentage',
      key: 'average_salary_growth_percentage',
      render: pct,
    },
  ];
}

const COURSE_GAP_COLUMNS = [
  {
    title: 'Programme',
    dataIndex: 'course_name',
    key: 'course_name',
    sorter: (a, b) => a.course_name.localeCompare(b.course_name),
  },
  {
    title: 'Follow-ups',
    dataIndex: 'total_followups',
    key: 'total_followups',
    align: 'right',
  },
  {
    title: 'Skill gap',
    dataIndex: 'skill_gap_percentage',
    key: 'skill_gap_percentage',
    width: 200,
    defaultSortOrder: 'descend',
    sorter: (a, b) => a.skill_gap_percentage - b.skill_gap_percentage,
    render: (value, row) => (
      <div>
        <PercentBar value={value} />
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.skill_gap_count} of {row.total_followups}
        </Text>
      </div>
    ),
  },
  {
    title: 'Needs more training',
    dataIndex: 'additional_training_percentage',
    key: 'additional_training_percentage',
    width: 200,
    sorter: (a, b) => a.additional_training_percentage - b.additional_training_percentage,
    render: (value, row) => (
      <div>
        <PercentBar value={value} />
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.additional_training_count} of {row.total_followups}
        </Text>
      </div>
    ),
  },
  {
    title: 'Relevance',
    dataIndex: 'average_training_relevance',
    key: 'average_training_relevance',
    render: rating,
  },
];

const DISTRICT_COLUMNS = [
  {
    title: 'District',
    dataIndex: 'district',
    key: 'district',
    sorter: (a, b) => a.district.localeCompare(b.district),
  },
  ...[
    ['trainee_count', 'Trainees'],
    ['completed_count', 'Completed'],
    ['unemployed_count', 'Unemployed'],
    ['skill_gap_count', 'Skill gaps'],
    ['additional_training_count', 'Need training'],
    ['non_placement_count', 'Non-placement'],
    ['attrition_count', 'Attrition'],
  ].map(([key, title]) => ({
    title,
    dataIndex: key,
    key,
    align: 'right',
    sorter: (a, b) => a[key] - b[key],
    ...(key === 'trainee_count' ? { defaultSortOrder: 'descend' } : {}),
  })),
];

function BreakdownTable({ data, error, columns, rowKey }) {
  if (error) return <SectionError error={error} />;
  return (
    <Table
      rowKey={rowKey}
      columns={columns}
      dataSource={data || []}
      size="middle"
      pagination={{ pageSize: 10, hideOnSinglePage: true }}
      scroll={{ x: 'max-content' }}
      locale={{ emptyText: <Empty description="No data yet" /> }}
    />
  );
}

function ReasonList({ reasons, emptyText }) {
  if (!reasons?.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />;
  }
  return (
    <List
      size="small"
      dataSource={reasons}
      renderItem={(r) => (
        <List.Item style={{ display: 'block' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Text>{r.reason}</Text>
            <Text type="secondary">{r.count}</Text>
          </div>
          <Progress percent={r.percentage} size="small" format={(p) => `${p.toFixed(1)}%`} />
        </List.Item>
      )}
    />
  );
}

// React StrictMode (development) mounts the page twice, which would fire every
// request twice. Both mounts share this one in-flight load instead; it is
// cleared once settled, so a later visit to the page still fetches fresh data.
let pendingLoad = null;

function loadInsights() {
  if (!pendingLoad) {
    pendingLoad = Promise.allSettled(
      Object.keys(ENDPOINTS).map((key) => api.get(ENDPOINTS[key]))
    ).finally(() => {
      pendingLoad = null;
    });
  }
  return pendingLoad;
}

export default function Insights() {
  const [data, setData] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.title = 'Insights — Skilling Outcomes Tracking System';
    let isMounted = true;

    async function fetchAll() {
      const keys = Object.keys(ENDPOINTS);
      const results = await loadInsights();
      if (!isMounted) return;

      const nextData = {};
      const nextErrors = {};
      results.forEach((result, i) => {
        const key = keys[i];
        if (result.status === 'fulfilled') {
          nextData[key] = result.value;
        } else {
          const detail = result.reason?.detail;
          nextErrors[key] = typeof detail === 'string' ? detail : 'Could not load this section.';
        }
      });
      setData(nextData);
      setErrors(nextErrors);
      setLoading(false);
    }

    fetchAll();

    return () => {
      isMounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '60px 0' }}>
        <Spin size="large" />
      </div>
    );
  }

  const { summary, remedial, accountability, nonPlacement, attrition, relevance, longitudinal, dataQuality } =
    data;
  const metrics = summary?.metrics;

  const funnel = longitudinal
    ? [
        { label: 'Training completed', value: longitudinal.training_completed },
        { label: '30-day follow-up done', value: longitudinal['30_day_followups_completed'] },
        { label: '90-day follow-up done', value: longitudinal['90_day_followups_completed'] },
        { label: '6-month follow-up done', value: longitudinal['6_month_followups_completed'] },
        { label: '12-month follow-up done', value: longitudinal['12_month_followups_completed'] },
        { label: 'Employed', value: longitudinal.employed_trainees },
        { label: 'Retained', value: longitudinal.retained_trainees },
      ]
    : [];
  const funnelBase = longitudinal?.training_completed || 0;

  const outcomeGapTotal = dataQuality
    ? DATA_QUALITY_GROUPS[0].items.reduce((sum, item) => sum + (dataQuality[item.key] || 0), 0)
    : 0;

  const breakdownTabs = [
    {
      key: 'programme',
      label: 'By programme',
      children: (
        <BreakdownTable
          data={accountability?.courses}
          error={errors.accountability}
          columns={accountabilityColumns('Programme')}
          rowKey="name"
        />
      ),
    },
    {
      key: 'provider',
      label: 'By provider',
      children: (
        <BreakdownTable
          data={accountability?.providers}
          error={errors.accountability}
          columns={accountabilityColumns('Provider')}
          rowKey="name"
        />
      ),
    },
    {
      key: 'skills',
      label: 'Skill gaps by programme',
      children: (
        <BreakdownTable
          data={data.courseGaps}
          error={errors.courseGaps}
          columns={COURSE_GAP_COLUMNS}
          rowKey="course_name"
        />
      ),
    },
    {
      key: 'district',
      label: 'By district',
      children: (
        <BreakdownTable
          data={data.districts}
          error={errors.districts}
          columns={DISTRICT_COLUMNS}
          rowKey="district"
        />
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Insights
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Rule-based findings on skill gaps, attrition and programme performance, plus a data-quality
          report. All figures are computed from recorded data; nothing is ranked or predicted.
        </Text>
      </div>

      <motion.div variants={containerVariants} initial="hidden" animate="visible">
        {/* Key metrics */}
        {errors.summary ? (
          <motion.div variants={itemVariants} style={{ marginBottom: 24 }}>
            <SectionError error={errors.summary} />
          </motion.div>
        ) : (
          metrics && (
            <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
              {[
                ['Skill gap', pct(metrics.skill_gap_percentage)],
                ['Need more training', pct(metrics.additional_training_percentage)],
                ['Avg. training relevance', rating(metrics.average_training_relevance)],
                ['Follow-up completion', pct(metrics.followup_completion_rate)],
              ].map(([label, value]) => (
                <Col xs={12} lg={6} key={label}>
                  <motion.div variants={itemVariants} style={{ height: '100%' }}>
                    <Stat label={label} value={value} />
                  </motion.div>
                </Col>
              ))}
            </Row>
          )
        )}

        {/* Rule-based insights + remedial actions */}
        <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
          <Col xs={24} lg={12}>
            <motion.div variants={itemVariants} style={{ height: '100%' }}>
              <Card
                style={{ ...cardStyle, height: '100%' }}
                title={
                  <span>
                    <BulbOutlined style={{ color: '#faad14', marginRight: 8 }} />
                    Findings
                  </span>
                }
              >
                {errors.summary ? (
                  <SectionError error={errors.summary} />
                ) : summary?.insights?.length ? (
                  <List
                    dataSource={summary.insights}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta
                          title={<Tag color="gold">{item.area}</Tag>}
                          description={<Text style={{ color: '#374151' }}>{item.observation}</Text>}
                        />
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty
                    image={<CheckCircleOutlined style={{ fontSize: 40, color: '#52c41a' }} />}
                    description="No metric has crossed an alert threshold."
                  />
                )}
              </Card>
            </motion.div>
          </Col>
          <Col xs={24} lg={12}>
            <motion.div variants={itemVariants} style={{ height: '100%' }}>
              <Card
                style={{ ...cardStyle, height: '100%' }}
                title={
                  <span>
                    <ToolOutlined style={{ color: '#1677ff', marginRight: 8 }} />
                    Suggested remedial actions
                  </span>
                }
              >
                {errors.remedial ? (
                  <SectionError error={errors.remedial} />
                ) : remedial?.length ? (
                  <List
                    dataSource={remedial}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                              <Tag color="blue">{item.area}</Tag>
                              {Object.entries(item.metric || {}).map(([k, v]) => (
                                <Tag key={k}>
                                  {METRIC_LABELS[k] || k}: {formatMetric(k, v)}
                                </Tag>
                              ))}
                            </div>
                          }
                          description={<Text style={{ color: '#374151' }}>{item.action}</Text>}
                        />
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No actions suggested" />
                )}
              </Card>
            </motion.div>
          </Col>
        </Row>

        {/* Breakdowns */}
        <motion.div variants={itemVariants} style={{ marginBottom: 24 }}>
          <Card style={cardStyle} title="Programme, provider & district indicators">
            <Tabs items={breakdownTabs} />
          </Card>
        </motion.div>

        {/* Reasons, relevance, longitudinal */}
        <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
          <Col xs={24} md={12} xl={8}>
            <motion.div variants={itemVariants} style={{ height: '100%' }}>
              <Card
                style={{ ...cardStyle, height: '100%' }}
                title="Non-placement reasons"
                extra={nonPlacement && <Text type="secondary">{nonPlacement.total_records} records</Text>}
              >
                {errors.nonPlacement ? (
                  <SectionError error={errors.nonPlacement} />
                ) : (
                  <ReasonList reasons={nonPlacement?.reasons} emptyText="No non-placement records" />
                )}
              </Card>
            </motion.div>
          </Col>
          <Col xs={24} md={12} xl={8}>
            <motion.div variants={itemVariants} style={{ height: '100%' }}>
              <Card
                style={{ ...cardStyle, height: '100%' }}
                title="Attrition"
                extra={attrition && <Tag color="volcano">{pct(attrition.attrition_rate)}</Tag>}
              >
                {errors.attrition ? (
                  <SectionError error={errors.attrition} />
                ) : attrition ? (
                  <>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
                      {attrition.attrition_records} of {attrition.total_employment_records} employment
                      records ended in leaving or termination.
                    </Text>
                    {!attrition.reason_data_available && attrition.attrition_records > 0 && (
                      <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 8 }}
                        message="Structured reason data isn't recorded for these exits yet."
                      />
                    )}
                    <ReasonList reasons={attrition.reasons} emptyText="No attrition reasons recorded" />
                  </>
                ) : null}
              </Card>
            </motion.div>
          </Col>
          <Col xs={24} md={12} xl={8}>
            <motion.div variants={itemVariants} style={{ height: '100%' }}>
              <Card
                style={{ ...cardStyle, height: '100%' }}
                title="Training relevance"
                extra={relevance && <Text type="secondary">{relevance.total_responses} responses</Text>}
              >
                {errors.relevance ? (
                  <SectionError error={errors.relevance} />
                ) : relevance?.total_responses ? (
                  <>
                    <div style={{ fontSize: 26, fontWeight: 600, color: '#1f2937', marginBottom: 12 }}>
                      {rating(relevance.average_rating)}
                    </div>
                    {[
                      ['High (4–5)', relevance.high_relevance_count, '#52c41a'],
                      ['Medium (3)', relevance.medium_relevance_count, '#faad14'],
                      ['Low (1–2)', relevance.low_relevance_count, '#ff4d4f'],
                    ].map(([label, count, color]) => (
                      <div key={label} style={{ marginBottom: 8 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                          <Text>{label}</Text>
                          <Text type="secondary">{count}</Text>
                        </div>
                        <Progress
                          percent={(count / relevance.total_responses) * 100}
                          showInfo={false}
                          strokeColor={color}
                          size="small"
                        />
                      </div>
                    ))}
                  </>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No relevance ratings yet" />
                )}
              </Card>
            </motion.div>
          </Col>
          <Col xs={24} md={12} xl={24}>
            <motion.div variants={itemVariants} style={{ height: '100%' }}>
              <Card style={{ ...cardStyle, height: '100%' }} title="Longitudinal outcomes">
                {errors.longitudinal ? (
                  <SectionError error={errors.longitudinal} />
                ) : funnelBase ? (
                  <>
                    <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
                      Counts at each stage, as a share of completed trainings.
                    </Text>
                    <Row gutter={[24, 8]}>
                      {funnel.map((stage) => (
                        <Col xs={24} xl={12} key={stage.label}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                            <Text>{stage.label}</Text>
                            <Text type="secondary">{stage.value}</Text>
                          </div>
                          <Progress
                            percent={Math.min((stage.value / funnelBase) * 100, 100)}
                            showInfo={false}
                            size="small"
                          />
                        </Col>
                      ))}
                    </Row>
                  </>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No completed trainings yet" />
                )}
              </Card>
            </motion.div>
          </Col>
        </Row>

        {/* Data quality */}
        <motion.div variants={itemVariants}>
          <Card
            style={cardStyle}
            title={
              <span>
                <WarningOutlined style={{ color: '#d46b08', marginRight: 8 }} />
                Data-quality report
              </span>
            }
          >
            {errors.dataQuality ? (
              <SectionError error={errors.dataQuality} />
            ) : dataQuality ? (
              <>
                {outcomeGapTotal > 0 ? (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 20 }}
                    message={`${outcomeGapTotal} gap(s) in outcome tracking`}
                    description="Completed trainings without an outcome, and employments without wage, verification or status history, make placement and retention figures less reliable."
                  />
                ) : (
                  <Alert
                    type="success"
                    showIcon
                    style={{ marginBottom: 20 }}
                    message="Outcome tracking is complete: every completed training has an outcome and every employment has wage, verification and status history."
                  />
                )}

                <Row gutter={[24, 24]}>
                  {DATA_QUALITY_GROUPS.map((group) => (
                    <Col xs={24} md={12} key={group.title}>
                      <Card
                        size="small"
                        title={group.title}
                        style={{
                          borderRadius: 10,
                          borderColor: group.highlight && outcomeGapTotal > 0 ? '#ffd591' : '#eef0f3',
                          backgroundColor: group.highlight && outcomeGapTotal > 0 ? '#fffbf0' : '#ffffff',
                          height: '100%',
                        }}
                      >
                        <List
                          size="small"
                          split={false}
                          dataSource={group.items}
                          renderItem={(item) => {
                            const count = dataQuality[item.key] ?? 0;
                            return (
                              <List.Item style={{ padding: '4px 0' }}>
                                <Text style={{ fontSize: 13 }}>{item.label}</Text>
                                <Tag
                                  color={count > 0 ? (group.highlight ? 'orange' : 'gold') : 'green'}
                                  style={{ margin: 0, minWidth: 36, textAlign: 'center' }}
                                >
                                  {count}
                                </Tag>
                              </List.Item>
                            );
                          }}
                        />
                      </Card>
                    </Col>
                  ))}
                </Row>

                <div style={{ marginTop: 20, display: 'flex', flexWrap: 'wrap', gap: 24 }}>
                  <div style={{ minWidth: 240 }}>
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      Follow-up completion rate
                    </Text>
                    <PercentBar
                      value={dataQuality.followup_completion_rate}
                      danger={dataQuality.followup_completion_rate < 50}
                    />
                  </div>
                  {dataQuality.trainees_consent_withdrawn_excluded > 0 && (
                    <Text type="secondary" style={{ fontSize: 13, alignSelf: 'center' }}>
                      <InfoCircleOutlined style={{ marginRight: 6 }} />
                      {dataQuality.trainees_consent_withdrawn_excluded} trainee(s) who withdrew consent
                      are excluded from all figures.
                    </Text>
                  )}
                </div>
              </>
            ) : null}
          </Card>
        </motion.div>
      </motion.div>
    </div>
  );
}
