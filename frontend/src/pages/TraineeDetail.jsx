import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Card,
  Tabs,
  Table,
  Badge,
  Modal,
  Spin,
  Typography,
  Button,
  Tag,
  Space,
  Descriptions,
  Empty,
  Alert,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { api } from '../api/client';

const { Title, Text, Paragraph } = Typography;

function updateRecentTrainees(trainee_id, full_name) {
  if (!trainee_id) return;
  try {
    const raw = sessionStorage.getItem('recentTrainees');
    let list = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(list)) list = [];
    list = list.filter((item) => item.trainee_id !== trainee_id);
    list.unshift({ trainee_id, full_name: full_name || trainee_id });
    list = list.slice(0, 10);
    sessionStorage.setItem('recentTrainees', JSON.stringify(list));
  } catch (e) {
    console.error('Failed to update recent trainees in sessionStorage', e);
  }
}

export default function TraineeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [trainee, setTrainee] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [consentModalVisible, setConsentModalVisible] = useState(false);
  const [updatingConsent, setUpdatingConsent] = useState(false);

  // Lazy loaded tab data & loading states
  const [activeTab, setActiveTab] = useState('overview');
  const [tabData, setTabData] = useState({
    training: null,
    outcomes: null,
    followups: null,
    employment: null,
    contact: null,
  });
  const [tabLoading, setTabLoading] = useState({
    training: false,
    outcomes: false,
    followups: false,
    employment: false,
    contact: false,
  });
  const [contactError, setContactError] = useState(null);

  const fetchTrainee = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setNotFound(false);

    try {
      const data = await api.get(`/api/trainees/${id}`);
      setTrainee(data);
      updateRecentTrainees(data.trainee_id, data.full_name);
    } catch (err) {
      if (err?.status === 404) {
        setNotFound(true);
      } else {
        message.error(err?.detail || 'Failed to load trainee profile');
        setNotFound(true);
      }
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchTrainee();
  }, [fetchTrainee]);

  // Tab change handler with lazy-loading
  const handleTabChange = async (key) => {
    setActiveTab(key);
    if (!id) return;

    if (key === 'training' && tabData.training === null && !tabLoading.training) {
      setTabLoading((prev) => ({ ...prev, training: true }));
      try {
        const res = await api.get(`/api/trainees/${id}/training-records`);
        const records = Array.isArray(res) ? res : res?.training_records || res?.records || [];
        setTabData((prev) => ({ ...prev, training: records }));
      } catch (err) {
        setTabData((prev) => ({ ...prev, training: [] }));
      } finally {
        setTabLoading((prev) => ({ ...prev, training: false }));
      }
    } else if (key === 'outcomes' && tabData.outcomes === null && !tabLoading.outcomes) {
      setTabLoading((prev) => ({ ...prev, outcomes: true }));
      try {
        const res = await api.get(`/api/trainees/${id}/outcomes`);
        const outcomes = Array.isArray(res) ? res : res?.outcomes || [];
        setTabData((prev) => ({ ...prev, outcomes }));
      } catch (err) {
        setTabData((prev) => ({ ...prev, outcomes: [] }));
      } finally {
        setTabLoading((prev) => ({ ...prev, outcomes: false }));
      }
    } else if (key === 'followups' && tabData.followups === null && !tabLoading.followups) {
      setTabLoading((prev) => ({ ...prev, followups: true }));
      try {
        const res = await api.get(`/api/trainees/${id}/followup-timeline`);
        const followups = Array.isArray(res) ? res : res?.followups || [];
        setTabData((prev) => ({ ...prev, followups }));
      } catch (err) {
        setTabData((prev) => ({ ...prev, followups: [] }));
      } finally {
        setTabLoading((prev) => ({ ...prev, followups: false }));
      }
    } else if (key === 'employment' && tabData.employment === null && !tabLoading.employment) {
      setTabLoading((prev) => ({ ...prev, employment: true }));
      try {
        const res = await api.get(`/api/trainees/${id}/employment-history`);
        const employment = Array.isArray(res) ? res : res?.employment_history || [];
        setTabData((prev) => ({ ...prev, employment }));
      } catch (err) {
        setTabData((prev) => ({ ...prev, employment: [] }));
      } finally {
        setTabLoading((prev) => ({ ...prev, employment: false }));
      }
    } else if (key === 'contact' && tabData.contact === null && !tabLoading.contact) {
      setTabLoading((prev) => ({ ...prev, contact: true }));
      setContactError(null);
      try {
        const res = await api.get(`/api/trainees/${id}/contact`);
        setTabData((prev) => ({ ...prev, contact: res }));
      } catch (err) {
        if (err?.status === 403) {
          setContactError('Not authorized to view contact details.');
        } else {
          setContactError(err?.detail || 'Failed to load contact information.');
        }
      } finally {
        setTabLoading((prev) => ({ ...prev, contact: false }));
      }
    }
  };

  const handleToggleConsent = async () => {
    if (!trainee) return;
    setUpdatingConsent(true);
    const newConsentStatus = !trainee.consent_given;

    try {
      await api.post(`/api/trainees/${id}/consent`, {
        consent_given: newConsentStatus,
      });
      message.success(
        `Consent successfully ${newConsentStatus ? 'granted' : 'withdrawn'}`
      );
      setConsentModalVisible(false);
      await fetchTrainee();
    } catch (err) {
      message.error(err?.detail || 'Failed to update consent');
    } finally {
      setUpdatingConsent(false);
    }
  };

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '50vh',
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  if (notFound || !trainee) {
    return (
      <div style={{ maxWidth: 600, margin: '60px auto', textAlign: 'center' }}>
        <Card style={{ borderRadius: 12, padding: '32px' }}>
          <Empty
            description={
              <div>
                <Title level={4} style={{ marginTop: 16 }}>
                  Trainee Not Found
                </Title>
                <Text type="secondary">
                  No trainee records matching ID <Text code>{id}</Text> were found in the database.
                </Text>
              </div>
            }
          >
            <Button
              type="primary"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/trainees')}
              style={{ marginTop: 16 }}
            >
              Back to Search
            </Button>
          </Empty>
        </Card>
      </div>
    );
  }

  // Column definitions for tabs
  const trainingColumns = [
    { title: 'Record ID', dataIndex: 'record_id', key: 'record_id', render: (val) => <Text code>{val}</Text> },
    { title: 'Course Name', dataIndex: 'course_name', key: 'course_name' },
    { title: 'Provider', dataIndex: 'provider_name', key: 'provider_name' },
    { title: 'Program', dataIndex: 'program_name', key: 'program_name', render: (v) => v || '—' },
    { title: 'Start Date', dataIndex: 'start_date', key: 'start_date' },
    { title: 'End Date', dataIndex: 'end_date', key: 'end_date', render: (v) => v || '—' },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (st) => (
        <Tag color={st === 'Completed' ? 'green' : st === 'Dropped' ? 'red' : 'blue'}>
          {st}
        </Tag>
      ),
    },
    {
      title: 'Assessment',
      dataIndex: 'assessment_status',
      key: 'assessment_status',
      render: (v) => v || '—',
    },
    {
      title: 'Certified',
      dataIndex: 'certification_issued',
      key: 'certification_issued',
      render: (issued) => (
        <Tag color={issued ? 'success' : 'default'}>{issued ? 'Yes' : 'No'}</Tag>
      ),
    },
  ];

  const outcomesColumns = [
    { title: 'Outcome ID', dataIndex: 'outcome_id', key: 'outcome_id', render: (val) => <Text code>{val}</Text> },
    { title: 'Training ID', dataIndex: 'training_id', key: 'training_id', render: (val) => <Text code>{val}</Text> },
    {
      title: 'Outcome Type',
      dataIndex: 'outcome_type',
      key: 'outcome_type',
      render: (t) => <Tag color="purple">{t}</Tag>,
    },
    { title: 'Status Date', dataIndex: 'status_date', key: 'status_date' },
  ];

  const followupsColumns = [
    { title: 'Follow-up ID', dataIndex: 'followup_id', key: 'followup_id', render: (val) => <Text code>{val}</Text> },
    { title: 'Training ID', dataIndex: 'training_id', key: 'training_id', render: (val) => <Text code>{val}</Text> },
    { title: 'Type', dataIndex: 'followup_type', key: 'followup_type' },
    { title: 'Scheduled Date', dataIndex: 'scheduled_date', key: 'scheduled_date' },
    { title: 'Completed Date', dataIndex: 'completed_date', key: 'completed_date', render: (v) => v || '—' },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (st) => (
        <Tag color={st === 'Completed' ? 'green' : st === 'Overdue' ? 'volcano' : 'gold'}>
          {st}
        </Tag>
      ),
    },
  ];

  const employmentColumns = [
    { title: 'Employment ID', dataIndex: 'employment_id', key: 'employment_id', render: (val) => <Text code>{val}</Text> },
    { title: 'Company Name', dataIndex: 'company_name', key: 'company_name' },
    { title: 'Job Role', dataIndex: 'job_role', key: 'job_role' },
    { title: 'Joining Date', dataIndex: 'joining_date', key: 'joining_date' },
    {
      title: 'Current Status',
      dataIndex: 'current_status',
      key: 'current_status',
      render: (st) => (
        <Tag color={st === 'Employed' ? 'green' : 'orange'}>{st}</Tag>
      ),
    },
  ];

  const tabItems = [
    {
      key: 'overview',
      label: 'Overview',
      children: (
        <Descriptions
          bordered
          column={{ xs: 1, sm: 2, md: 2 }}
          size="middle"
          style={{ marginTop: 8 }}
        >
          <Descriptions.Item label="Gender">{trainee.gender || '—'}</Descriptions.Item>
          <Descriptions.Item label="Date of Birth">{trainee.dob || '—'}</Descriptions.Item>
          <Descriptions.Item label="District">{trainee.district || '—'}</Descriptions.Item>
          <Descriptions.Item label="Town / Area">
            {trainee.current_location || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Preferred Contact">
            <Tag color="cyan">{trainee.preferred_contact || '—'}</Tag>
          </Descriptions.Item>
        </Descriptions>
      ),
    },
    {
      key: 'training',
      label: 'Training',
      children: tabLoading.training ? (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin />
        </div>
      ) : (
        <Table
          rowKey={(r) => r.record_id || Math.random()}
          columns={trainingColumns}
          dataSource={tabData.training || []}
          locale={{ emptyText: 'No training records yet' }}
          pagination={{ pageSize: 5 }}
          scroll={{ x: true }}
        />
      ),
    },
    {
      key: 'outcomes',
      label: 'Outcomes',
      children: tabLoading.outcomes ? (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin />
        </div>
      ) : (
        <Table
          rowKey={(r) => r.outcome_id || Math.random()}
          columns={outcomesColumns}
          dataSource={tabData.outcomes || []}
          locale={{ emptyText: 'No outcomes recorded yet' }}
          pagination={{ pageSize: 5 }}
          scroll={{ x: true }}
        />
      ),
    },
    {
      key: 'followups',
      label: 'Follow-ups',
      children: tabLoading.followups ? (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin />
        </div>
      ) : (
        <Table
          rowKey={(r) => r.followup_id || Math.random()}
          columns={followupsColumns}
          dataSource={tabData.followups || []}
          locale={{ emptyText: 'No follow-up records yet' }}
          pagination={{ pageSize: 5 }}
          scroll={{ x: true }}
        />
      ),
    },
    {
      key: 'employment',
      label: 'Employment',
      children: tabLoading.employment ? (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin />
        </div>
      ) : (
        <Table
          rowKey={(r) => r.employment_id || Math.random()}
          columns={employmentColumns}
          dataSource={tabData.employment || []}
          locale={{ emptyText: 'No employment records yet' }}
          pagination={{ pageSize: 5 }}
          scroll={{ x: true }}
        />
      ),
    },
    {
      key: 'contact',
      label: 'Contact',
      children: tabLoading.contact ? (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin />
        </div>
      ) : contactError ? (
        <Alert
          type="warning"
          message={contactError}
          showIcon
          style={{ borderRadius: 6, margin: '8px 0' }}
        />
      ) : tabData.contact ? (
        <Descriptions bordered column={1} size="middle" style={{ marginTop: 8 }}>
          <Descriptions.Item label="Mobile Number">
            {tabData.contact.phone || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Email Address">
            {tabData.contact.email || '—'}
          </Descriptions.Item>
        </Descriptions>
      ) : null,
    },
  ];

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      {/* Back Link */}
      <div style={{ marginBottom: 16 }}>
        <Link to="/trainees">
          <Button type="link" icon={<ArrowLeftOutlined />} style={{ padding: 0 }}>
            Back to Trainee Search
          </Button>
        </Link>
      </div>

      {/* Trainee Header Card */}
      <Card
        style={{
          borderRadius: 12,
          border: '1px solid #eef0f3',
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
          marginBottom: 24,
        }}
        styles={{ body: { padding: '24px 28px' } }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div>
            <Space align="center" size={12}>
              <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
                {trainee.full_name}
              </Title>
              <Text code style={{ fontSize: 14 }}>
                {trainee.trainee_id}
              </Text>
            </Space>
            <div style={{ marginTop: 4 }}>
              <Text type="secondary">District: {trainee.district}</Text>
            </div>
          </div>

          <Space size={12} align="center">
            {trainee.consent_given ? (
              <Tag
                icon={<CheckCircleOutlined />}
                color="success"
                style={{ padding: '4px 10px', fontSize: 13 }}
              >
                Consent given
              </Tag>
            ) : (
              <Tag
                icon={<CloseCircleOutlined />}
                color="error"
                style={{ padding: '4px 10px', fontSize: 13 }}
              >
                Consent withdrawn
              </Tag>
            )}

            <Button
              icon={<SwapOutlined />}
              onClick={() => setConsentModalVisible(true)}
            >
              Change consent
            </Button>
          </Space>
        </div>
      </Card>

      {/* Tabbed Content */}
      <Card
        style={{
          borderRadius: 12,
          border: '1px solid #eef0f3',
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
        }}
        styles={{ body: { padding: '20px 24px' } }}
      >
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={tabItems}
        />
      </Card>

      {/* Consent Change Confirmation Modal */}
      <Modal
        title="Confirm Consent Update"
        open={consentModalVisible}
        onOk={handleToggleConsent}
        confirmLoading={updatingConsent}
        onCancel={() => setConsentModalVisible(false)}
        okText={trainee.consent_given ? 'Withdraw Consent' : 'Grant Consent'}
        okButtonProps={{ danger: trainee.consent_given }}
      >
        <Space direction="vertical" size={12} style={{ margin: '16px 0' }}>
          <Space align="start">
            <ExclamationCircleOutlined
              style={{ color: trainee.consent_given ? '#ff4d4f' : '#faad14', fontSize: 22 }}
            />
            <div>
              <Paragraph style={{ margin: 0 }}>
                Are you sure you want to{' '}
                <Text strong>{trainee.consent_given ? 'withdraw consent' : 'grant consent'}</Text>{' '}
                for <Text strong>{trainee.full_name}</Text> ({trainee.trainee_id})?
              </Paragraph>
              {trainee.consent_given && (
                <Paragraph type="secondary" style={{ marginTop: 8, fontSize: 13 }}>
                  Withdrawing consent will stop further automated outreach and follow-up activities.
                </Paragraph>
              )}
            </div>
          </Space>
        </Space>
      </Modal>
    </div>
  );
}
