import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Card,
  Table,
  Tag,
  Button,
  Typography,
  Input,
  Select,
  Drawer,
  Descriptions,
  Row,
  Col,
  Statistic,
  Spin,
  Alert,
  Empty,
  Tooltip,
} from 'antd';
import {
  ReloadOutlined,
  SearchOutlined,
  RiseOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const { Title, Text } = Typography;

const LIST_LIMIT = 1000;

const SOURCE_COLORS = {
  Trainee: 'orange',
  Employer: 'green',
  Document: 'blue',
  Admin: 'purple',
};

const SOURCE_OPTIONS = Object.keys(SOURCE_COLORS).map((value) => ({ value, label: value }));

const VERIFICATION_OPTIONS = [
  { value: 'Verified', label: 'Verified' },
  { value: 'Unverified', label: 'Unverified' },
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

function formatAmount(value) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatDate(value) {
  if (!value) return '—';
  return new Date(`${value}T00:00:00`).toLocaleDateString();
}

function monthly(record) {
  return record.salary_period === 'Annual' ? record.salary / 12 : record.salary;
}

function SourceTags({ source, status }) {
  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
      <Tag color={SOURCE_COLORS[source] || 'default'} style={{ margin: 0 }}>
        {source}
      </Tag>
      {status === 'Verified' ? (
        <Tag icon={<CheckCircleOutlined />} color="success" style={{ margin: 0 }}>
          Verified
        </Tag>
      ) : (
        <Tag style={{ margin: 0 }}>Unverified</Tag>
      )}
    </div>
  );
}

/** One employment's salary progression, using the backend's summary (monthly-normalised). */
function EmploymentProgression({ employment }) {
  const [summary, setSummary] = useState(null);
  const [points, setPoints] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const id = encodeURIComponent(employment.employment_id);

    async function fetchProgression() {
      try {
        const [summaryRes, historyRes] = await Promise.all([
          api.get(`/api/employment/${id}/summary`),
          api.get(`/api/employment/${id}/wage-history`),
        ]);
        if (isMounted) {
          setSummary(summaryRes);
          setPoints(historyRes?.wage_history || []);
        }
      } catch (err) {
        if (isMounted) setError(err?.detail || 'Failed to load wage progression.');
      }
    }

    fetchProgression();

    return () => {
      isMounted = false;
    };
  }, [employment.employment_id]);

  const salary = summary?.salary;
  const growth = salary?.growth_percentage;

  return (
    <Card
      size="small"
      style={{ borderRadius: 10, marginBottom: 16 }}
      title={
        <span>
          {employment.company_name}{' '}
          <Text type="secondary" style={{ fontWeight: 400 }}>
            · {employment.job_role}
          </Text>
        </span>
      }
      extra={<Tag>{employment.current_status}</Tag>}
    >
      {error ? (
        <Alert type="error" showIcon message={error} />
      ) : !summary ? (
        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <Spin />
        </div>
      ) : (
        <>
          <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
            {employment.employment_id} · joined {formatDate(employment.joining_date)}
          </Text>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} md={8}>
              <Statistic
                title="First (monthly)"
                value={formatAmount(salary?.initial_monthly)}
                styles={{ content: { fontSize: 20 } }}
              />
              {salary?.initial_period === 'Annual' && (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {formatAmount(salary.initial)} / year
                </Text>
              )}
            </Col>
            <Col xs={12} md={8}>
              <Statistic
                title="Latest (monthly)"
                value={formatAmount(salary?.latest_monthly)}
                styles={{ content: { fontSize: 20 } }}
              />
              {salary?.period === 'Annual' && (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {formatAmount(salary.latest)} / year
                </Text>
              )}
            </Col>
            <Col xs={24} md={8}>
              <Statistic
                title="Growth"
                value={growth ?? '—'}
                precision={growth !== null && growth !== undefined ? 1 : undefined}
                suffix={growth !== null && growth !== undefined ? '%' : undefined}
                styles={{
                  content: {
                    fontSize: 20,
                    color:
                      growth === null || growth === undefined
                        ? undefined
                        : growth >= 0
                        ? '#3f8600'
                        : '#cf1322',
                  },
                }}
                prefix={
                  growth === null || growth === undefined ? null : growth >= 0 ? (
                    <ArrowUpOutlined />
                  ) : (
                    <ArrowDownOutlined />
                  )
                }
              />
            </Col>
          </Row>
          <Table
            rowKey="wage_record_id"
            size="small"
            pagination={false}
            dataSource={points}
            locale={{ emptyText: 'No wage records for this employment' }}
            scroll={{ x: 'max-content' }}
            columns={[
              { title: 'Effective', dataIndex: 'effective_date', key: 'effective_date', render: formatDate },
              {
                title: 'Salary',
                key: 'salary',
                align: 'right',
                render: (_, r) => `${formatAmount(r.salary)} / ${r.salary_period === 'Annual' ? 'yr' : 'mo'}`,
              },
              {
                title: 'Source',
                key: 'source',
                render: (_, r) => <SourceTags source={r.source} status={r.verification_status} />,
              },
            ]}
          />
        </>
      )}
    </Card>
  );
}

/** All employments of one trainee, each with its wage progression. */
function TraineeWageProgression({ traineeId }) {
  const [employments, setEmployments] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;

    async function fetchEmployments() {
      try {
        const res = await api.get(
          `/api/trainees/${encodeURIComponent(traineeId)}/employment-history`
        );
        if (isMounted) setEmployments(res?.employment_history || []);
      } catch (err) {
        if (isMounted) setError(err?.detail || 'Failed to load employment history.');
      }
    }

    fetchEmployments();

    return () => {
      isMounted = false;
    };
  }, [traineeId]);

  if (error) return <Alert type="error" showIcon message={error} />;
  if (!employments) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0' }}>
        <Spin />
      </div>
    );
  }
  if (employments.length === 0) {
    return <Empty description="No employment records for this trainee" />;
  }

  return (
    <>
      <Alert
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ marginBottom: 16 }}
        message="Growth compares the first and latest wage record of each job. Annual salaries are divided by 12 so they can be compared."
      />
      {employments.map((e) => (
        <EmploymentProgression key={e.employment_id} employment={e} />
      ))}
    </>
  );
}

export default function WageHistory() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState(null);
  const [statusFilter, setStatusFilter] = useState(null);

  const [selectedTrainee, setSelectedTrainee] = useState(null);

  useEffect(() => {
    document.title = 'Wage History — Skilling Outcomes Tracking System';
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function fetchRecords() {
      const params = new URLSearchParams({ limit: String(LIST_LIMIT) });
      if (sourceFilter) params.set('source', sourceFilter);
      if (statusFilter) params.set('verification_status', statusFilter);
      try {
        const data = await api.get(`/api/wage-history?${params}`);
        if (isMounted) {
          setRecords(Array.isArray(data) ? data : []);
          setLoadError(null);
        }
      } catch (err) {
        if (isMounted) setLoadError(err?.detail || 'Failed to load wage records.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchRecords();

    return () => {
      isMounted = false;
    };
  }, [sourceFilter, statusFilter, reloadKey]);

  const reload = useCallback(() => {
    setLoading(true);
    setReloadKey((k) => k + 1);
  }, []);

  const changeSource = (value) => {
    setLoading(true);
    setSourceFilter(value ?? null);
  };

  const changeStatus = (value) => {
    setLoading(true);
    setStatusFilter(value ?? null);
  };

  const term = search.trim().toLowerCase();
  const filtered = term
    ? records.filter((r) =>
        [r.trainee_id, r.trainee_name, r.company_name, r.employment_id]
          .filter(Boolean)
          .some((v) => v.toLowerCase().includes(term))
      )
    : records;

  const columns = [
    {
      title: 'Trainee',
      key: 'trainee',
      sorter: (a, b) => (a.trainee_name || '').localeCompare(b.trainee_name || ''),
      render: (_, r) => (
        <div>
          <Link to={`/trainees/${r.trainee_id}`}>{r.trainee_name || r.trainee_id}</Link>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {r.trainee_id}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: 'Employer',
      key: 'employer',
      sorter: (a, b) => (a.company_name || '').localeCompare(b.company_name || ''),
      render: (_, r) => (
        <div>
          {r.company_name || '—'}
          {r.job_role && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {r.job_role}
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: 'Salary',
      dataIndex: 'salary',
      key: 'salary',
      align: 'right',
      sorter: (a, b) => monthly(a) - monthly(b),
      render: (value, r) => (
        <div>
          {formatAmount(value)}
          {r.salary_period === 'Annual' && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                ≈ {formatAmount(value / 12)} / mo
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: 'Period',
      dataIndex: 'salary_period',
      key: 'salary_period',
      render: (value) => <Tag color={value === 'Annual' ? 'geekblue' : 'default'}>{value}</Tag>,
    },
    {
      title: 'Effective date',
      dataIndex: 'effective_date',
      key: 'effective_date',
      render: formatDate,
      defaultSortOrder: 'descend',
      sorter: (a, b) => a.effective_date.localeCompare(b.effective_date),
    },
    {
      title: 'Source',
      key: 'source',
      render: (_, r) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <SourceTags source={r.source} status={r.verification_status} />
          {r.notes && (
            <Tooltip title={r.notes}>
              <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
            </Tooltip>
          )}
        </div>
      ),
    },
    {
      title: 'Action',
      key: 'action',
      fixed: 'right',
      render: (_, r) => (
        <Button
          size="small"
          icon={<RiseOutlined />}
          onClick={() => setSelectedTrainee({ id: r.trainee_id, name: r.trainee_name })}
        >
          Progression
        </Button>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div
        style={{
          marginBottom: 28,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          flexWrap: 'wrap',
          gap: 16,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
            Wage History
          </Title>
          <Text type="secondary" style={{ fontSize: 14 }}>
            Every recorded salary point across trainees. Earlier figures are never overwritten, so
            progression can be traced over time.
          </Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={reload} disabled={loading}>
          Refresh
        </Button>
      </div>

      <motion.div variants={containerVariants} initial="hidden" animate="visible">
        <motion.div variants={itemVariants}>
          <Card style={cardStyle} title="Wage records">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder="Search trainee, ID, or employer"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ width: 280 }}
              />
              <Select
                allowClear
                placeholder="Source"
                options={SOURCE_OPTIONS}
                value={sourceFilter}
                onChange={changeSource}
                style={{ width: 160 }}
              />
              <Select
                allowClear
                placeholder="Verification"
                options={VERIFICATION_OPTIONS}
                value={statusFilter}
                onChange={changeStatus}
                style={{ width: 160 }}
              />
            </div>

            {loadError ? (
              <Alert type="error" showIcon message={loadError} />
            ) : (
              <>
                <Table
                  rowKey="wage_record_id"
                  columns={columns}
                  dataSource={filtered}
                  loading={loading}
                  size="middle"
                  pagination={{ pageSize: 10, hideOnSinglePage: true }}
                  scroll={{ x: 'max-content' }}
                  locale={{ emptyText: <Empty description="No wage records" /> }}
                />
                {records.length >= LIST_LIMIT && (
                  <Text type="secondary" style={{ display: 'block', marginTop: 12, fontSize: 12 }}>
                    Showing the {LIST_LIMIT} most recent records. Use the filters to narrow down.
                  </Text>
                )}
              </>
            )}
          </Card>
        </motion.div>
      </motion.div>

      {/* Trainee Wage Progression Drawer */}
      <Drawer
        title={
          selectedTrainee
            ? `Wage progression — ${selectedTrainee.name || selectedTrainee.id}`
            : 'Wage progression'
        }
        open={Boolean(selectedTrainee)}
        onClose={() => setSelectedTrainee(null)}
        size="large"
        destroyOnHidden
      >
        {selectedTrainee && (
          <>
            <Descriptions size="small" column={1} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="Trainee">
                <Link to={`/trainees/${selectedTrainee.id}`}>{selectedTrainee.id}</Link>
              </Descriptions.Item>
            </Descriptions>
            <TraineeWageProgression traineeId={selectedTrainee.id} />
          </>
        )}
      </Drawer>
    </div>
  );
}
