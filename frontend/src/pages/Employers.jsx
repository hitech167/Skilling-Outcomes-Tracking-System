import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Card,
  Table,
  Tag,
  Button,
  Typography,
  Row,
  Col,
  Segmented,
  Drawer,
  Descriptions,
  Modal,
  Spin,
  Alert,
  Empty,
  message,
} from 'antd';
import {
  BellOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const { Title, Text } = Typography;

const STATUSES = [
  { value: 'Pending', color: 'gold', icon: <ClockCircleOutlined /> },
  { value: 'Verified', color: 'green', icon: <CheckCircleOutlined /> },
  { value: 'Rejected', color: 'red', icon: <CloseCircleOutlined /> },
  { value: 'Unable to Verify', color: 'default', icon: <QuestionCircleOutlined /> },
];

const STATUS_COLORS = Object.fromEntries(STATUSES.map((s) => [s.value, s.color]));

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

function StatusTag({ status }) {
  return <Tag color={STATUS_COLORS[status] || 'default'}>{status}</Tag>;
}

function formatDate(value) {
  if (!value) return '—';
  return new Date(value).toLocaleDateString();
}

function formatSalary(value) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export default function Employers() {
  const [verifications, setVerifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('All');

  const [remindModalVisible, setRemindModalVisible] = useState(false);
  const [reminding, setReminding] = useState(false);
  const [remindSummary, setRemindSummary] = useState(null);

  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    document.title = 'Employers — Skilling Outcomes Tracking System';
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function fetchVerifications() {
      try {
        const data = await api.get('/api/employer-verifications?limit=1000');
        if (isMounted) {
          setVerifications(data);
          setLoadError(null);
        }
      } catch (err) {
        if (isMounted) setLoadError(err?.detail || 'Failed to load employer verifications.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchVerifications();

    return () => {
      isMounted = false;
    };
  }, [reloadKey]);

  const reload = useCallback(() => {
    setLoading(true);
    setReloadKey((k) => k + 1);
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    let isMounted = true;

    async function fetchDetail() {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const data = await api.get(
          `/api/employer-verifications/${encodeURIComponent(selectedId)}`
        );
        if (isMounted) setDetail(data);
      } catch (err) {
        if (isMounted) setDetailError(err?.detail || 'Failed to load verification.');
      } finally {
        if (isMounted) setDetailLoading(false);
      }
    }

    fetchDetail();

    return () => {
      isMounted = false;
    };
  }, [selectedId]);

  const closeDetail = () => {
    setSelectedId(null);
    setDetail(null);
    setDetailError(null);
  };

  const handleRemind = async () => {
    setReminding(true);
    try {
      const summary = await api.post('/api/employer-verifications/remind-pending', {});
      setRemindSummary(summary);
      setRemindModalVisible(false);
      if (summary.reminded > 0) {
        message.success(`Reminders created for ${summary.reminded} employer(s).`);
      } else {
        message.info('No pending verifications could be reminded automatically.');
      }
    } catch (err) {
      message.error(err?.detail || 'Failed to send reminders.');
    } finally {
      setReminding(false);
    }
  };

  const counts = STATUSES.reduce((acc, s) => {
    acc[s.value] = verifications.filter((v) => v.verification_status === s.value).length;
    return acc;
  }, {});
  const pendingCount = counts.Pending || 0;

  const filtered =
    statusFilter === 'All'
      ? verifications
      : verifications.filter((v) => v.verification_status === statusFilter);

  const columns = [
    {
      title: 'Verification ID',
      dataIndex: 'verification_id',
      key: 'verification_id',
      render: (id) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => setSelectedId(id)}>
          {id}
        </Button>
      ),
    },
    {
      title: 'Employer',
      dataIndex: 'employer_name',
      key: 'employer_name',
      sorter: (a, b) => a.employer_name.localeCompare(b.employer_name),
    },
    {
      title: 'Trainee',
      key: 'trainee',
      render: (_, row) => (
        <Link to={`/trainees/${row.trainee_id}`}>{row.trainee_name || row.trainee_id}</Link>
      ),
    },
    {
      title: 'Job role',
      dataIndex: 'job_role',
      key: 'job_role',
      render: (value) => value || '—',
    },
    {
      title: 'Salary',
      dataIndex: 'salary',
      key: 'salary',
      align: 'right',
      render: formatSalary,
    },
    {
      title: 'Method',
      dataIndex: 'verification_method',
      key: 'verification_method',
    },
    {
      title: 'Status',
      dataIndex: 'verification_status',
      key: 'verification_status',
      render: (status) => <StatusTag status={status} />,
    },
    {
      title: 'Requested',
      dataIndex: 'created_at',
      key: 'created_at',
      render: formatDate,
      sorter: (a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0),
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
            Employers
          </Title>
          <Text type="secondary" style={{ fontSize: 14 }}>
            Track employer verification requests and follow up on pending confirmations.
          </Text>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button icon={<ReloadOutlined />} onClick={reload} disabled={loading}>
            Refresh
          </Button>
          <Button
            type="primary"
            icon={<BellOutlined />}
            onClick={() => setRemindModalVisible(true)}
            disabled={loading || pendingCount === 0}
          >
            Remind pending
          </Button>
        </div>
      </div>

      <motion.div variants={containerVariants} initial="hidden" animate="visible">
        {/* Status summary cards */}
        <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
          {STATUSES.map((s) => (
            <Col xs={12} lg={6} key={s.value}>
              <motion.div variants={itemVariants} style={{ height: '100%' }}>
                <Card
                  hoverable
                  onClick={() => setStatusFilter(s.value)}
                  style={{
                    ...cardStyle,
                    height: '100%',
                    borderColor: statusFilter === s.value ? '#1677ff' : '#eef0f3',
                  }}
                  styles={{ body: { padding: 20 } }}
                >
                  <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>
                    {s.icon} {s.value}
                  </Text>
                  <div style={{ fontSize: 28, fontWeight: 600, color: '#1f2937', marginTop: 4 }}>
                    {loading ? <Spin size="small" /> : counts[s.value]}
                  </div>
                </Card>
              </motion.div>
            </Col>
          ))}
        </Row>

        {remindSummary && (
          <motion.div variants={itemVariants} style={{ marginBottom: 24 }}>
            <Alert
              type={remindSummary.failed > 0 ? 'warning' : 'info'}
              showIcon
              closable
              onClose={() => setRemindSummary(null)}
              message={`Reminders: ${remindSummary.reminded} of ${remindSummary.pending} pending verification(s)`}
              description={
                <>
                  {remindSummary.sent} sent, {remindSummary.queued} queued in the outbox,{' '}
                  {remindSummary.failed} failed.
                  {remindSummary.skipped_no_contact > 0 &&
                    ` ${remindSummary.skipped_no_contact} skipped (no employer contact).`}
                  {remindSummary.skipped_not_link_based > 0 &&
                    ` ${remindSummary.skipped_not_link_based} skipped (verified by other methods; follow up manually).`}
                </>
              }
            />
          </motion.div>
        )}

        {/* Verification table */}
        <motion.div variants={itemVariants}>
          <Card
            style={cardStyle}
            title="Verification requests"
            extra={
              <Segmented
                value={statusFilter}
                onChange={setStatusFilter}
                options={['All', ...STATUSES.map((s) => s.value)]}
              />
            }
          >
            {loadError ? (
              <Alert type="error" showIcon message={loadError} />
            ) : (
              <Table
                rowKey="verification_id"
                columns={columns}
                dataSource={filtered}
                loading={loading}
                size="middle"
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
                scroll={{ x: 'max-content' }}
                locale={{ emptyText: <Empty description="No verification requests" /> }}
              />
            )}
          </Card>
        </motion.div>
      </motion.div>

      {/* Remind Pending Confirmation Modal */}
      <Modal
        title="Remind pending employers?"
        open={remindModalVisible}
        onOk={handleRemind}
        confirmLoading={reminding}
        onCancel={() => setRemindModalVisible(false)}
        okText="Send reminders"
      >
        <p>
          This re-sends the confirmation link to every employer whose latest verification is
          still <StatusTag status="Pending" /> ({pendingCount} record(s) in total).
        </p>
        <p style={{ marginBottom: 0 }}>
          Only link-based requests with an employer contact can be reminded automatically.
          Messages go to the notification outbox if no email/SMS provider is configured.
        </p>
      </Modal>

      {/* Verification Detail Drawer */}
      <Drawer
        title={selectedId ? `Verification ${selectedId}` : 'Verification'}
        open={Boolean(selectedId)}
        onClose={closeDetail}
        size="large"
      >
        {detailLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
            <Spin />
          </div>
        ) : detailError ? (
          <Alert type="error" showIcon message={detailError} />
        ) : detail ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="Status">
              <StatusTag status={detail.verification_status} />
            </Descriptions.Item>
            <Descriptions.Item label="Employer">{detail.employer_name}</Descriptions.Item>
            <Descriptions.Item label="Employer contact">
              {detail.employer_contact || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="Trainee">
              <Link to={`/trainees/${detail.trainee_id}`}>
                {detail.trainee_name || detail.trainee_id}
              </Link>{' '}
              <Text type="secondary">({detail.trainee_id})</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Employment ID">{detail.employment_id}</Descriptions.Item>
            <Descriptions.Item label="Job role">{detail.job_role || '—'}</Descriptions.Item>
            <Descriptions.Item label="Salary">{formatSalary(detail.salary)}</Descriptions.Item>
            <Descriptions.Item label="Method">{detail.verification_method}</Descriptions.Item>
            <Descriptions.Item label="Requested">{formatDate(detail.created_at)}</Descriptions.Item>
            <Descriptions.Item label="Verified on">{formatDate(detail.verified_date)}</Descriptions.Item>
            <Descriptions.Item label="Verified by">{detail.verified_by || '—'}</Descriptions.Item>
            <Descriptions.Item label="Notes">{detail.verification_notes || '—'}</Descriptions.Item>
          </Descriptions>
        ) : null}
      </Drawer>
    </div>
  );
}
