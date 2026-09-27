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
  Form,
  Input,
  Space,
  message,
} from 'antd';
import {
  BellOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { api, errorMessage } from '../api/client';
import SendVerificationModal from '../components/SendVerificationModal';

const { Title, Text } = Typography;

const STATUSES = [
  { value: 'Pending', color: 'gold', icon: <ClockCircleOutlined /> },
  { value: 'Verified', color: 'green', icon: <CheckCircleOutlined /> },
  { value: 'Rejected', color: 'red', icon: <CloseCircleOutlined /> },
  { value: 'Unable to Verify', color: 'default', icon: <QuestionCircleOutlined /> },
];

const STATUS_COLORS = Object.fromEntries(STATUSES.map((s) => [s.value, s.color]));

// Staff decisions on a Pending request (PATCH /api/employer-verifications/{id}/status)
const DECISIONS = {
  Verified: { label: 'Confirm', okText: 'Confirm employment', danger: false },
  Rejected: { label: 'Reject', okText: 'Reject', danger: true },
  'Unable to Verify': { label: 'Unable to verify', okText: 'Mark unable to verify', danger: false },
};

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

  const [decision, setDecision] = useState(null);
  const [deciding, setDeciding] = useState(false);
  const [decisionError, setDecisionError] = useState(null);
  const [decisionForm] = Form.useForm();

  const [sendOpen, setSendOpen] = useState(false);

  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    document.title = 'Employers — Skilling Outcomes Tracking System';
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function fetchVerifications() {
      try {
        // Shared: StrictMode (development) runs this mount effect twice
        const data = await api.getShared('/api/employer-verifications?limit=1000');
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
        const data = await api.getShared(
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

  const openDecision = (status) => {
    setDecisionError(null);
    decisionForm.resetFields();
    setDecision(status);
  };

  const handleDecision = async (values) => {
    setDeciding(true);
    setDecisionError(null);
    try {
      const updated = await api.patch(
        `/api/employer-verifications/${encodeURIComponent(detail.verification_id)}/status`,
        {
          verification_status: decision,
          verified_by: values.verified_by?.trim() || null,
          verification_notes: values.verification_notes?.trim() || null,
        }
      );
      setDetail(updated);
      setVerifications((prev) =>
        prev.map((v) => (v.verification_id === updated.verification_id ? updated : v))
      );
      setDecision(null);
      message.success(`Verification ${updated.verification_id} marked ${updated.verification_status}.`);
    } catch (err) {
      setDecisionError(errorMessage(err, 'Failed to update the verification.'));
    } finally {
      setDeciding(false);
    }
  };

  const handleRemind = async () => {
    setReminding(true);
    try {
      const summary = await api.post('/api/verifications/remind-pending', {});
      setRemindSummary(summary);
      setRemindModalVisible(false);
      if (summary.reminded > 0) {
        message.success(`Reminders created for ${summary.reminded} employer(s).`);
      } else {
        message.info('No employers were due a reminder.');
      }
      // Unresponsive employers are moved to "Unable to Verify"
      if (summary.marked_unresponsive > 0) reload();
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
              type="info"
              showIcon
              closable
              onClose={() => setRemindSummary(null)}
              message={`${remindSummary.reminded} reminder(s) created`}
              description={
                <>
                  Check the Messages page for delivery status.
                  {remindSummary.marked_unresponsive > 0 &&
                    ` ${remindSummary.marked_unresponsive} marked Unable to Verify (employer unresponsive).`}
                  {remindSummary.skipped_no_contact > 0 &&
                    ` ${remindSummary.skipped_no_contact} skipped (no employer contact).`}
                  {remindSummary.skipped_no_consent > 0 &&
                    ` ${remindSummary.skipped_no_consent} skipped (trainee withdrew consent).`}
                  {remindSummary.skipped_superseded > 0 &&
                    ` ${remindSummary.skipped_superseded} older request(s) skipped (replaced by a newer request for the same job).`}
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
          This re-sends the confirmation link to employers whose verification is still{' '}
          <StatusTag status="Pending" /> ({pendingCount} record(s) in total) and who were last
          contacted more than 7 days ago.
        </p>
        <p style={{ marginBottom: 0 }}>
          Employers that have already had 3 requests with no answer are marked Unable to Verify
          instead. Trainees who withdrew consent are skipped.
        </p>
      </Modal>

      {/* Verification Detail Drawer */}
      <Drawer
        title={selectedId ? `Verification ${selectedId}` : 'Verification'}
        open={Boolean(selectedId)}
        onClose={closeDetail}
        size="large"
        extra={
          detail && (
            <Button icon={<SendOutlined />} onClick={() => setSendOpen(true)}>
              Send new request
            </Button>
          )
        }
      >
        {detailLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
            <Spin />
          </div>
        ) : detailError ? (
          <Alert type="error" showIcon message={detailError} />
        ) : detail ? (
          <>
            {detail.verification_status === 'Pending' && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="Waiting for the employer"
                description="Confirmed by phone or document instead? Record the decision here."
                action={
                  <Space direction="vertical" size={6}>
                    {Object.entries(DECISIONS).map(([status, d]) => (
                      <Button
                        key={status}
                        size="small"
                        block
                        type={status === 'Verified' ? 'primary' : 'default'}
                        danger={d.danger}
                        onClick={() => openDecision(status)}
                      >
                        {d.label}
                      </Button>
                    ))}
                  </Space>
                }
              />
            )}
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
          </>
        ) : null}
      </Drawer>

      {/* Staff decision on a Pending verification */}
      <Modal
        title={decision ? `Mark as ${decision}?` : ''}
        open={Boolean(decision)}
        onOk={() => decisionForm.submit()}
        okText={decision && DECISIONS[decision].okText}
        okButtonProps={{ danger: decision && DECISIONS[decision].danger }}
        confirmLoading={deciding}
        onCancel={() => !deciding && setDecision(null)}
        destroyOnHidden
      >
        {decisionError && (
          <Alert type="error" showIcon message={decisionError} style={{ marginBottom: 16 }} />
        )}
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          This closes the request; the employer's link will no longer accept an answer.
        </Text>
        <Form form={decisionForm} layout="vertical" onFinish={handleDecision}>
          <Form.Item label="Verified by" name="verified_by" rules={[{ max: 150 }]}>
            <Input placeholder="e.g. R. Deshmukh, HR Manager (phone)" />
          </Form.Item>
          <Form.Item label="Notes" name="verification_notes" rules={[{ max: 2000 }]}>
            <Input.TextArea rows={3} placeholder="How was this confirmed?" />
          </Form.Item>
        </Form>
      </Modal>

      <SendVerificationModal
        open={sendOpen}
        employment={
          detail && {
            employment_id: detail.employment_id,
            company_name: detail.employer_name,
            job_role: detail.job_role,
          }
        }
        defaultContact={detail?.employer_contact}
        onClose={() => setSendOpen(false)}
        onSent={reload}
      />
    </div>
  );
}
