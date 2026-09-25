import { useEffect, useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Card,
  Tabs,
  Table,
  Button,
  Tag,
  Space,
  Statistic,
  Row,
  Col,
  Modal,
  Form,
  Input,
  Select,
  DatePicker,
  message,
  Alert,
  Typography,
  Dropdown,
  Spin,
  Empty,
  Descriptions,
  Checkbox,
} from 'antd';
import {
  SendOutlined,
  MoreOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  PhoneOutlined,
  ReloadOutlined,
  ExclamationCircleOutlined,
  SearchOutlined,
  UserOutlined,
  CloseOutlined,
  PlusOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import { api } from '../api/client';

const { Title, Text, Paragraph } = Typography;

function formatKeyLabel(key) {
  if (!key) return '';
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function getStatColor(key) {
  const lower = key.toLowerCase();
  if (lower.includes('overdue') || lower.includes('missed') || lower.includes('failed')) {
    return '#cf1322';
  }
  if (lower.includes('complete')) {
    return '#389e0d';
  }
  if (lower.includes('upcoming')) {
    return '#0958d9';
  }
  if (lower.includes('pending') || lower.includes('scheduled')) {
    return '#d46b08';
  }
  return '#1f2937';
}

function outcomeTypeColor(type) {
  const map = {
    '30_day': 'blue',
    '90_day': 'cyan',
    '6_month': 'purple',
    '12_month': 'geekblue',
    '3-month': 'blue',
    '6-month': 'purple',
    '12-month': 'geekblue',
    initial: 'green',
  };
  return map[type?.toLowerCase()] || 'default';
}

export default function Followups() {
  const navigate = useNavigate();

  // Summary state
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  // Dispatch state
  const [dispatching, setDispatching] = useState(false);
  const [dispatchResultModal, setDispatchResultModal] = useState(null);

  // Tabs state & lazy-loading data
  const [activeTab, setActiveTab] = useState('overdue');
  const [tabData, setTabData] = useState({
    overdue: null,
    upcoming: null,
    pending: null,
  });
  const [tabLoading, setTabLoading] = useState({
    overdue: false,
    upcoming: false,
    pending: false,
  });
  const [tabError, setTabError] = useState({
    overdue: null,
    upcoming: null,
    pending: null,
  });

  // Action states
  const [actionLoadingId, setActionLoadingId] = useState(null);

  // Log attempt modal state (row-level)
  const [attemptModalVisible, setAttemptModalVisible] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [submittingAttempt, setSubmittingAttempt] = useState(false);
  const [attemptForm] = Form.useForm();

  // Trainee ID search / filter state
  const [searchInput, setSearchInput] = useState('');
  const [activeSearch, setActiveSearch] = useState('');

  // Direct follow-up (Log Direct Follow-up) modal state
  const [directModalVisible, setDirectModalVisible] = useState(false);
  const [directTraineeFollowups, setDirectTraineeFollowups] = useState([]);
  const [directFollowupsLoading, setDirectFollowupsLoading] = useState(false);
  const [submittingDirect, setSubmittingDirect] = useState(false);
  const [directForm] = Form.useForm();

  // Schedule Follow-up modal state
  const [scheduleModalVisible, setScheduleModalVisible] = useState(false);
  const [scheduleTrainingRecords, setScheduleTrainingRecords] = useState([]);
  const [scheduleTrainingLoading, setScheduleTrainingLoading] = useState(false);
  const [submittingSchedule, setSubmittingSchedule] = useState(false);
  const [scheduleForm] = Form.useForm();

  // Set document title
  useEffect(() => {
    document.title = 'Follow-up Queue — Skilling Outcomes Tracking System';
  }, []);

  // Fetch summary counts
  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const res = await api.get('/api/followups/summary');
      setSummary(res && typeof res === 'object' ? res : {});
    } catch {
      setSummary({});
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  // Fetch tab data
  const fetchTabFollowups = useCallback(async (tabKey) => {
    setTabLoading((prev) => ({ ...prev, [tabKey]: true }));
    setTabError((prev) => ({ ...prev, [tabKey]: null }));

    try {
      const res = await api.get(`/api/followups/${tabKey}`);
      const list = Array.isArray(res) ? res : [];
      setTabData((prev) => ({ ...prev, [tabKey]: list }));
    } catch (err) {
      const msg = err?.detail || `Failed to load ${tabKey} follow-ups`;
      setTabError((prev) => ({ ...prev, [tabKey]: msg }));
      setTabData((prev) => ({ ...prev, [tabKey]: [] }));
    } finally {
      setTabLoading((prev) => ({ ...prev, [tabKey]: false }));
    }
  }, []);

  // Fetch initial tab data on mount or when tab changes
  useEffect(() => {
    if (tabData[activeTab] === null) {
      fetchTabFollowups(activeTab);
    }
  }, [activeTab, tabData, fetchTabFollowups]);

  // Handle Tab Switch
  const handleTabChange = (key) => {
    setActiveTab(key);
    if (tabData[key] === null) {
      fetchTabFollowups(key);
    }
  };

  // Dispatch all due check-ins
  const handleDispatchDue = async () => {
    setDispatching(true);
    try {
      const res = await api.post('/api/followups/dispatch-due');
      
      let summaryText = 'Check-ins dispatched successfully.';
      if (res && typeof res === 'object') {
        const parts = [];
        if (res.due_followups !== undefined) parts.push(`Due: ${res.due_followups}`);
        if (res.sent !== undefined) parts.push(`Sent: ${res.sent}`);
        if (res.queued !== undefined) parts.push(`Queued: ${res.queued}`);
        if (res.failed !== undefined) parts.push(`Failed: ${res.failed}`);
        if (parts.length > 0) {
          summaryText = parts.join(' | ');
        } else if (res.message) {
          summaryText = res.message;
        }
      }
      
      message.success(summaryText);
      setDispatchResultModal(res);

      // Refresh current tab and summary counts
      fetchSummary();
      fetchTabFollowups(activeTab);
    } catch (err) {
      message.error(err?.detail || 'Failed to dispatch due check-ins');
    } finally {
      setDispatching(false);
    }
  };

  // Immediate row actions (Mark Complete, Mark Missed, Mark Not Reachable)
  const handleImmediateAction = async (record, actionType) => {
    const { followup_id } = record;
    setActionLoadingId(`${followup_id}_${actionType}`);

    const endpointMap = {
      complete: `/api/followups/${followup_id}/complete`,
      missed: `/api/followups/${followup_id}/missed`,
      not_reachable: `/api/followups/${followup_id}/not-reachable`,
    };

    const labelMap = {
      complete: 'Marked as Completed',
      missed: 'Marked as Missed',
      not_reachable: 'Marked as Not Reachable',
    };

    try {
      await api.post(endpointMap[actionType]);
      message.success(labelMap[actionType]);

      // Remove row immediately from current tab's table
      setTabData((prev) => ({
        ...prev,
        [activeTab]: (prev[activeTab] || []).filter((item) => item.followup_id !== followup_id),
      }));

      // Update summary counts silently
      fetchSummary();
    } catch (err) {
      message.error(err?.detail || `Failed to update follow-up status`);
    } finally {
      setActionLoadingId(null);
    }
  };

  // Open Log Attempt Modal
  const openLogAttemptModal = (record) => {
    setSelectedRecord(record);
    attemptForm.resetFields();
    setAttemptModalVisible(true);
  };

  // Submit Log Attempt
  const handleAttemptSubmit = async () => {
    try {
      const values = await attemptForm.validateFields();
      if (!selectedRecord?.followup_id) return;

      const sendNotif = values.send_notification !== false;
      setSubmittingAttempt(true);
      const res = await api.post(`/api/followups/${selectedRecord.followup_id}/attempt`, {
        notes: values.notes,
        send_notification: sendNotif,
      });

      const isEmailSent = Boolean(res?.email_sent ?? res?.message_sent);
      if (isEmailSent) {
        message.success(res?.message || 'Attempt logged and email notification sent successfully.');
      } else if (sendNotif) {
        message.warning(res?.message || 'Attempt logged in database, but email notification could not be sent.');
      } else {
        message.success(res?.message || 'Contact attempt logged successfully');
      }
      setAttemptModalVisible(false);
      attemptForm.resetFields();
      setSelectedRecord(null);
    } catch (err) {
      if (err?.errorFields) return;
      message.error(err?.detail || 'Failed to log contact attempt');
    } finally {
      setSubmittingAttempt(false);
    }
  };

  // ── Search handlers ──────────────────────────────────────────────────────

  const handleSearch = (value) => {
    const trimmed = value.trim();
    setActiveSearch(trimmed);
  };

  const handleClearSearch = () => {
    setSearchInput('');
    setActiveSearch('');
  };

  // ── Direct Follow-up Modal ────────────────────────────────────────────────

  const openDirectFollowupModal = () => {
    directForm.resetFields();
    // Pre-fill trainee_id if there is an active search
    if (activeSearch) {
      directForm.setFieldsValue({ trainee_id: activeSearch });
    }
    setDirectTraineeFollowups([]);
    setDirectModalVisible(true);
  };

  // When trainee ID is entered in the direct modal, fetch their scheduled follow-ups
  const fetchDirectTraineeFollowups = async (traineeId) => {
    if (!traineeId?.trim()) {
      setDirectTraineeFollowups([]);
      return;
    }
    setDirectFollowupsLoading(true);
    try {
      const res = await api.get(`/api/trainees/${traineeId.trim()}/followups`);
      const list = Array.isArray(res) ? res : res?.followups || [];
      // Only show Scheduled ones
      const scheduled = list.filter((f) => f.status === 'Scheduled' || !f.status);
      setDirectTraineeFollowups(scheduled);
      if (scheduled.length === 0) {
        message.info('No scheduled follow-ups found for this trainee.');
      }
    } catch (err) {
      message.error(err?.detail || 'Could not load trainee follow-ups.');
      setDirectTraineeFollowups([]);
    } finally {
      setDirectFollowupsLoading(false);
    }
  };

  const handleDirectFollowupSubmit = async () => {
    try {
      const values = await directForm.validateFields();
      if (!values.followup_id) {
        message.warning('Please select a follow-up to log an attempt against.');
        return;
      }
      const sendNotif = values.send_notification !== false;
      setSubmittingDirect(true);
      const res = await api.post(`/api/followups/${values.followup_id}/attempt`, {
        notes: values.notes,
        send_notification: sendNotif,
      });
      const isEmailSent = Boolean(res?.email_sent ?? res?.message_sent);
      if (isEmailSent) {
        message.success(res?.message || 'Attempt logged and email notification sent successfully.');
      } else if (sendNotif) {
        message.warning(res?.message || 'Attempt logged in database, but email notification could not be sent.');
      } else {
        message.success(res?.message || 'Follow-up attempt logged successfully.');
      }
      setDirectModalVisible(false);
      directForm.resetFields();
      setDirectTraineeFollowups([]);
      // Refresh current tab
      fetchTabFollowups(activeTab);
    } catch (err) {
      if (err?.errorFields) return;
      message.error(err?.detail || 'Failed to log follow-up attempt.');
    } finally {
      setSubmittingDirect(false);
    }
  };

  // ── Schedule Follow-up handlers ──────────────────────────────────────────

  const openScheduleModal = () => {
    scheduleForm.resetFields();
    // Pre-fill trainee_id from active search if present
    if (activeSearch) {
      scheduleForm.setFieldsValue({ trainee_id: activeSearch });
    }
    setScheduleTrainingRecords([]);
    setScheduleModalVisible(true);
  };

  // Fetch training records for a trainee so staff can pick a training_id
  const fetchScheduleTrainingRecords = async (traineeId) => {
    if (!traineeId?.trim()) {
      setScheduleTrainingRecords([]);
      return;
    }
    setScheduleTrainingLoading(true);
    try {
      const res = await api.get(`/api/trainees/${traineeId.trim()}/training-records`);
      const list = Array.isArray(res) ? res : res?.training_records || res?.records || [];
      setScheduleTrainingRecords(list);
      if (list.length === 0) {
        message.info('No training records found for this trainee.');
      }
    } catch (err) {
      message.error(err?.detail || 'Could not load training records.');
      setScheduleTrainingRecords([]);
    } finally {
      setScheduleTrainingLoading(false);
    }
  };

  const handleScheduleSubmit = async () => {
    try {
      const values = await scheduleForm.validateFields();
      setSubmittingSchedule(true);

      const payload = {
        trainee_id: values.trainee_id.trim().toUpperCase(),
        training_id: values.training_id,
        followup_type: values.followup_type,
        scheduled_date: values.scheduled_date.format('YYYY-MM-DD'),
        notes: values.notes || null,
      };

      await api.post('/api/followups', payload);
      message.success('Follow-up scheduled successfully.');
      scheduleForm.resetFields();
      setScheduleTrainingRecords([]);
      setScheduleModalVisible(false);
      // Refresh tabs so the new follow-up appears
      setTabData((prev) => ({ ...prev, upcoming: null, pending: null }));
      if (activeTab === 'upcoming' || activeTab === 'pending') {
        fetchTabFollowups(activeTab);
      }
      fetchSummary();
    } catch (err) {
      if (err?.errorFields) return;
      message.error(err?.detail || 'Failed to schedule follow-up.');
    } finally {
      setSubmittingSchedule(false);
    }
  };

  // Columns definition
  const columns = [
    {
      title: 'Trainee ID',
      dataIndex: 'trainee_id',
      key: 'trainee_id',
      width: 170,
      render: (trainee_id) => (
        <Link
          to={`/trainees/${trainee_id}`}
          style={{ fontWeight: 600, color: '#1677ff' }}
        >
          {trainee_id}
        </Link>
      ),
    },
    {
      title: 'Follow-up Type',
      dataIndex: 'followup_type',
      key: 'followup_type',
      width: 160,
      render: (type) => (
        <Tag color={outcomeTypeColor(type)} style={{ fontWeight: 500 }}>
          {type || 'Standard'}
        </Tag>
      ),
    },
    {
      title: 'Scheduled Date',
      dataIndex: 'scheduled_date',
      key: 'scheduled_date',
      width: 150,
      render: (date) => (
        <Text style={{ fontSize: 13 }}>{date || '—'}</Text>
      ),
    },
    ...(activeTab === 'overdue'
      ? [
          {
            title: 'Days Overdue',
            dataIndex: 'days_overdue',
            key: 'days_overdue',
            width: 140,
            render: (days) => (
              <Tag
                color="error"
                style={{
                  fontWeight: 600,
                  fontSize: 12,
                  padding: '2px 8px',
                }}
              >
                {days !== undefined && days !== null ? `${days} day${days === 1 ? '' : 's'}` : 'Overdue'}
              </Tag>
            ),
          },
        ]
      : []),
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_, record) => {
        const isRowLoading = actionLoadingId && actionLoadingId.startsWith(record.followup_id);

        const menuItems = [
          {
            key: 'complete',
            label: 'Mark Complete',
            icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
            onClick: () => handleImmediateAction(record, 'complete'),
          },
          {
            key: 'missed',
            label: 'Mark Missed',
            icon: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
            onClick: () => handleImmediateAction(record, 'missed'),
          },
          {
            key: 'not_reachable',
            label: 'Mark Not Reachable',
            icon: <StopOutlined style={{ color: '#fa8c16' }} />,
            onClick: () => handleImmediateAction(record, 'not_reachable'),
          },
          {
            type: 'divider',
          },
          {
            key: 'attempt',
            label: 'Log Attempt',
            icon: <PhoneOutlined style={{ color: '#1677ff' }} />,
            onClick: () => openLogAttemptModal(record),
          },
        ];

        return (
          <Space size={8}>
            <Button
              size="small"
              type="primary"
              icon={<PhoneOutlined />}
              onClick={() => openLogAttemptModal(record)}
            >
              Log Attempt
            </Button>
            <Dropdown
              menu={{ items: menuItems }}
              trigger={['click']}
              disabled={isRowLoading}
            >
              <Button size="small" icon={<MoreOutlined />} loading={isRowLoading}>
                Actions
              </Button>
            </Dropdown>
          </Space>
        );
      },
    },
  ];

  const emptyTextMap = {
    overdue: 'No overdue follow-ups',
    upcoming: 'No upcoming follow-ups',
    pending: 'No pending follow-ups',
  };

  const currentList = tabData[activeTab] || [];
  const currentLoading = tabLoading[activeTab];
  const currentError = tabError[activeTab];

  // Filtered list — client-side filter by trainee_id when activeSearch is set
  const filteredList = activeSearch
    ? currentList.filter((item) =>
        item.trainee_id?.toLowerCase().includes(activeSearch.toLowerCase())
      )
    : currentList;

  const emptyDescription = activeSearch
    ? `No follow-ups found for Trainee ID: "${activeSearch}"`
    : emptyTextMap[activeTab] || 'No records found';

  // Render generic stat cards from summary
  const summaryEntries = summary && typeof summary === 'object' ? Object.entries(summary) : [];

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      {/* Page Header & Action Button */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
            Follow-up Queue
          </Title>
          <Text type="secondary" style={{ fontSize: 14 }}>
            Monitor and manage milestone check-ins, record outreach outcomes, and log contact attempts.
          </Text>
        </div>

        <Button
          type="primary"
          size="large"
          icon={<SendOutlined />}
          loading={dispatching}
          onClick={handleDispatchDue}
          style={{
            fontWeight: 600,
            borderRadius: 8,
            boxShadow: '0 2px 6px rgba(22, 119, 255, 0.2)',
          }}
        >
          Send all due check-ins now
        </Button>
      </div>

      {/* Summary Strip (Generically rendered) */}
      <div style={{ marginBottom: 24 }}>
        {summaryLoading ? (
          <Card
            size="small"
            style={{
              borderRadius: 12,
              textAlign: 'center',
              padding: '20px 0',
              border: '1px solid #eef0f3',
            }}
          >
            <Spin size="small" /> <Text type="secondary" style={{ marginLeft: 8 }}>Loading summary...</Text>
          </Card>
        ) : summaryEntries.length > 0 ? (
          <Row gutter={[16, 16]}>
            {summaryEntries.map(([key, value]) => (
              <Col
                key={key}
                xs={12}
                sm={8}
                md={Math.max(4, Math.floor(24 / summaryEntries.length))}
                lg={Math.max(4, Math.floor(24 / summaryEntries.length))}
              >
                <Card
                  size="small"
                  style={{
                    borderRadius: 10,
                    border: '1px solid #eef0f3',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
                    backgroundColor: '#ffffff',
                  }}
                  styles={{ body: { padding: '12px 16px' } }}
                >
                  <Statistic
                    title={
                      <Text
                        type="secondary"
                        style={{
                          fontSize: 12,
                          textTransform: 'uppercase',
                          fontWeight: 600,
                          letterSpacing: '0.4px',
                        }}
                      >
                        {formatKeyLabel(key)}
                      </Text>
                    }
                    value={typeof value === 'number' ? value : String(value ?? 0)}
                    valueStyle={{
                      fontSize: 22,
                      fontWeight: 700,
                      color: getStatColor(key),
                    }}
                  />
                </Card>
              </Col>
            ))}
          </Row>
        ) : null}
      </div>

      {/* Search Bar + Toolbar */}
      <Card
        size="small"
        style={{
          borderRadius: 12,
          border: '1px solid #eef0f3',
          marginBottom: 16,
          boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
        }}
        styles={{ body: { padding: '14px 20px' } }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          {/* Search / Filter input */}
          <Input.Search
            id="followup-trainee-search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onSearch={handleSearch}
            placeholder="Filter by Trainee ID..."
            allowClear={false}
            enterButton={
              <Button type="primary" icon={<SearchOutlined />}>
                Filter
              </Button>
            }
            style={{ maxWidth: 360, flex: '1 1 260px' }}
          />

          {/* Active filter badge + actions */}
          {activeSearch && (
            <Space size={8} wrap>
              <Tag
                color="blue"
                icon={<UserOutlined />}
                style={{ fontSize: 13, padding: '3px 10px', borderRadius: 6 }}
              >
                {activeSearch}
              </Tag>
              <Button
                size="small"
                icon={<UserOutlined />}
                type="link"
                onClick={() => navigate(`/trainees/${activeSearch}`)}
                style={{ padding: 0, fontWeight: 600 }}
              >
                View Profile
              </Button>
              <Button
                size="small"
                icon={<CloseOutlined />}
                onClick={handleClearSearch}
                style={{ color: '#8c8c8c' }}
              >
                Clear
              </Button>
            </Space>
          )}

          {/* Right-side action buttons */}
          <Space size={8} style={{ marginLeft: 'auto' }}>
            <Button
              icon={<PhoneOutlined />}
              onClick={openDirectFollowupModal}
              style={{ borderColor: '#1677ff', color: '#1677ff' }}
            >
              Log Attempt
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openScheduleModal}
              style={{ fontWeight: 600 }}
            >
              Schedule Follow-up
            </Button>
          </Space>
        </div>
      </Card>

      {/* Main Tabs Component */}
      <Card
        style={{
          borderRadius: 12,
          border: '1px solid #eef0f3',
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
        }}
        styles={{ body: { padding: '8px 20px 20px 20px' } }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderBottom: '1px solid #f0f0f0',
            marginBottom: 16,
          }}
        >
          <Tabs
            activeKey={activeTab}
            onChange={handleTabChange}
            style={{ flex: 1, marginBottom: -1 }}
            items={[
              {
                key: 'overdue',
                label: (
                  <span style={{ fontWeight: 600 }}>
                    <ExclamationCircleOutlined style={{ color: '#ff4d4f', marginRight: 6 }} />
                    Overdue
                  </span>
                ),
              },
              {
                key: 'upcoming',
                label: (
                  <span style={{ fontWeight: 600 }}>
                    Upcoming
                  </span>
                ),
              },
              {
                key: 'pending',
                label: (
                  <span style={{ fontWeight: 600 }}>
                    Pending
                  </span>
                ),
              },
            ]}
          />

          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => fetchTabFollowups(activeTab)}
            loading={currentLoading}
            style={{ color: '#595959' }}
          >
            Refresh
          </Button>
        </div>

        {currentError && (
          <Alert
            type="error"
            message={currentError}
            showIcon
            style={{ marginBottom: 16, borderRadius: 8 }}
          />
        )}

        <Table
          rowKey="followup_id"
          columns={columns}
          dataSource={filteredList}
          loading={currentLoading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50'],
            showTotal: (total, range) =>
              `${range[0]}-${range[1]} of ${total} follow-up${total === 1 ? '' : 's'}${
                activeSearch ? ` for "${activeSearch}"` : ''
              }`,
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <span style={{ color: '#8c8c8c' }}>{emptyDescription}</span>
                }
              />
            ),
          }}
          scroll={{ x: 750 }}
          size="middle"
        />
      </Card>

      {/* Log Contact Attempt Modal */}
      <Modal
        title="Log Contact Attempt"
        open={attemptModalVisible}
        onCancel={() => {
          if (!submittingAttempt) {
            setAttemptModalVisible(false);
            attemptForm.resetFields();
            setSelectedRecord(null);
          }
        }}
        onOk={handleAttemptSubmit}
        confirmLoading={submittingAttempt}
        destroyOnClose
        okText="Log Attempt"
        centered
      >
        <div style={{ marginBottom: 16, marginTop: 8 }}>
          <Text type="secondary">
            Log outreach notes for Trainee:{' '}
            <strong style={{ color: '#1677ff' }}>
              {selectedRecord?.trainee_id}
            </strong>
          </Text>
          {selectedRecord?.followup_type && (
            <div style={{ marginTop: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Milestone: <strong>{selectedRecord.followup_type}</strong>
              </Text>
            </div>
          )}
        </div>

        <Form form={attemptForm} layout="vertical">
          <Form.Item
            name="notes"
            label="Outreach Notes"
            rules={[
              { required: true, message: 'Please enter notes about the contact attempt' },
              { min: 3, message: 'Notes must be at least 3 characters' },
            ]}
          >
            <Input.TextArea
              rows={4}
              placeholder="e.g. Called trainee on mobile. Trainee confirmed they are still at current employer..."
              maxLength={1000}
              showCount
            />
          </Form.Item>

          <Form.Item
            name="send_notification"
            valuePropName="checked"
            initialValue={true}
            style={{ marginBottom: 0 }}
          >
            <Checkbox>Send notification copy to Trainee</Checkbox>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Log Direct Follow-up Modal ─────────────────────────────────── */}
      <Modal
        title="Log Direct Follow-up Attempt"
        open={directModalVisible}
        onCancel={() => {
          if (!submittingDirect) {
            setDirectModalVisible(false);
            directForm.resetFields();
            setDirectTraineeFollowups([]);
          }
        }}
        onOk={handleDirectFollowupSubmit}
        confirmLoading={submittingDirect}
        okText="Log Attempt"
        destroyOnClose
        centered
        width={520}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 16, marginTop: 4 }}>
          Search for a trainee's scheduled follow-ups and log a contact attempt.
        </Text>
        <Form form={directForm} layout="vertical">
          <Form.Item
            name="trainee_id"
            label="Trainee ID"
            rules={[{ required: true, message: 'Please enter a Trainee ID' }]}
          >
            <Input.Search
              placeholder="e.g. TR-00042"
              enterButton={
                <Button
                  icon={<SearchOutlined />}
                  loading={directFollowupsLoading}
                >
                  Find Follow-ups
                </Button>
              }
              onSearch={(val) => {
                directForm.setFieldsValue({ trainee_id: val, followup_id: undefined });
                fetchDirectTraineeFollowups(val);
              }}
              allowClear
            />
          </Form.Item>

          {directTraineeFollowups.length > 0 && (
            <Form.Item
              name="followup_id"
              label="Select Follow-up"
              rules={[{ required: true, message: 'Please select a follow-up' }]}
            >
              <Select placeholder="Select a scheduled follow-up...">
                {directTraineeFollowups.map((f) => (
                  <Select.Option key={f.followup_id} value={f.followup_id}>
                    {f.followup_type || 'Standard'} — {f.scheduled_date || 'No date'}
                    {f.days_overdue ? ` (${f.days_overdue}d overdue)` : ''}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          )}

          <Form.Item
            name="notes"
            label="Outreach Notes"
            rules={[
              { required: true, message: 'Please enter notes about the contact attempt' },
              { min: 3, message: 'Notes must be at least 3 characters' },
            ]}
          >
            <Input.TextArea
              rows={4}
              placeholder="e.g. Called trainee. They confirmed placement is still ongoing..."
              maxLength={1000}
              showCount
            />
          </Form.Item>

          <Form.Item
            name="send_notification"
            valuePropName="checked"
            initialValue={true}
            style={{ marginBottom: 0 }}
          >
            <Checkbox>Send notification copy to Trainee</Checkbox>
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Schedule Follow-up Modal ────────────────────────────────────── */}
      <Modal
        title={
          <Space>
            <CalendarOutlined style={{ color: '#1677ff' }} />
            Schedule Follow-up
          </Space>
        }
        open={scheduleModalVisible}
        onCancel={() => {
          if (!submittingSchedule) {
            setScheduleModalVisible(false);
            scheduleForm.resetFields();
            setScheduleTrainingRecords([]);
          }
        }}
        onOk={handleScheduleSubmit}
        confirmLoading={submittingSchedule}
        okText="Schedule"
        destroyOnClose
        centered
        width={540}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 16, marginTop: 4 }}>
          Schedule a new milestone check-in for a trainee's training record.
        </Text>
        <Form form={scheduleForm} layout="vertical">
          {/* Trainee ID — with lookup button */}
          <Form.Item
            name="trainee_id"
            label="Trainee ID"
            rules={[{ required: true, message: 'Please enter a Trainee ID' }]}
          >
            <Input.Search
              placeholder="e.g. TRN000001"
              enterButton={
                <Button icon={<SearchOutlined />} loading={scheduleTrainingLoading}>
                  Load Records
                </Button>
              }
              onSearch={(val) => {
                scheduleForm.setFieldsValue({ trainee_id: val, training_id: undefined });
                fetchScheduleTrainingRecords(val);
              }}
              allowClear
            />
          </Form.Item>

          {/* Training ID — populated after lookup */}
          <Form.Item
            name="training_id"
            label="Training Record"
            rules={[{ required: true, message: 'Please select a training record' }]}
            extra={
              scheduleTrainingRecords.length === 0 && !scheduleTrainingLoading
                ? 'Enter a Trainee ID above and click "Load Records" first'
                : null
            }
          >
            <Select
              placeholder="Select a training record..."
              loading={scheduleTrainingLoading}
              disabled={scheduleTrainingRecords.length === 0}
              notFoundContent="No records found"
            >
              {scheduleTrainingRecords.map((rec) => (
                <Select.Option key={rec.record_id} value={rec.record_id}>
                  {rec.record_id}
                  {rec.course_name ? ` — ${rec.course_name}` : ''}
                  {rec.status ? ` (${rec.status})` : ''}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          {/* Follow-up Type */}
          <Form.Item
            name="followup_type"
            label="Follow-up Type"
            rules={[{ required: true, message: 'Please select a follow-up type' }]}
          >
            <Select placeholder="Select milestone type...">
              <Select.Option value="30_DAY">30-Day Check-in</Select.Option>
              <Select.Option value="90_DAY">90-Day Check-in</Select.Option>
              <Select.Option value="6_MONTH">6-Month Check-in</Select.Option>
              <Select.Option value="12_MONTH">12-Month Check-in</Select.Option>
            </Select>
          </Form.Item>

          {/* Scheduled Date */}
          <Form.Item
            name="scheduled_date"
            label="Scheduled Date"
            rules={[{ required: true, message: 'Please select a date' }]}
          >
            <DatePicker
              style={{ width: '100%' }}
              format="YYYY-MM-DD"
              placeholder="Select date"
            />
          </Form.Item>

          {/* Notes */}
          <Form.Item name="notes" label="Notes (Optional)">
            <Input.TextArea
              rows={3}
              placeholder="Any context or reason for this check-in..."
              maxLength={500}
              showCount
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Dispatch Result Details Modal (Optional detail view) */}
      {dispatchResultModal && (
        <Modal
          title="Check-ins Dispatch Summary"
          open={!!dispatchResultModal}
          onOk={() => setDispatchResultModal(null)}
          onCancel={() => setDispatchResultModal(null)}
          footer={[
            <Button key="close" type="primary" onClick={() => setDispatchResultModal(null)}>
              Done
            </Button>,
          ]}
          centered
        >
          <div style={{ padding: '8px 0' }}>
            {typeof dispatchResultModal === 'object' ? (
              <Descriptions bordered size="small" column={1}>
                {Object.entries(dispatchResultModal).map(([k, v]) => (
                  <Descriptions.Item key={k} label={formatKeyLabel(k)}>
                    <strong>{String(v)}</strong>
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Paragraph>{String(dispatchResultModal)}</Paragraph>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
