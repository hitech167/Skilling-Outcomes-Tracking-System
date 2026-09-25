import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Card,
  Tabs,
  Table,
  Modal,
  Spin,
  Typography,
  Button,
  Tag,
  Space,
  Descriptions,
  Empty,
  Alert,
  Form,
  Input,
  DatePicker,
  Select,
  InputNumber,
  Switch,
  message,
} from 'antd';
import {
  ArrowLeftOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SwapOutlined,
  PlusOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { api } from '../api/client';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

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

  // Add Training Record Modal State
  const [addRecordModalVisible, setAddRecordModalVisible] = useState(false);
  const [addingRecord, setAddingRecord] = useState(false);
  const [addRecordError, setAddRecordError] = useState(null);
  const [addRecordForm] = Form.useForm();
  const certIssued = Form.useWatch('certification_issued', addRecordForm);

  // Add Outcome Modal State
  const [addOutcomeModalVisible, setAddOutcomeModalVisible] = useState(false);
  const [addingOutcome, setAddingOutcome] = useState(false);
  const [addOutcomeError, setAddOutcomeError] = useState(null);
  const [addOutcomeForm] = Form.useForm();
  const selectedOutcomeType = Form.useWatch('outcome_type', addOutcomeForm);

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
    if (trainee) {
      document.title = `${trainee.full_name} (${trainee.trainee_id}) — Skilling Outcomes Tracking System`;
    } else {
      document.title = "Trainee Profile — Skilling Outcomes Tracking System";
    }
  }, [trainee]);

  useEffect(() => {
    fetchTrainee();
  }, [fetchTrainee]);

  const fetchTrainingRecords = useCallback(async () => {
    if (!id) return;
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
  }, [id]);

  const fetchOutcomes = useCallback(async () => {
    if (!id) return;
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
  }, [id]);

  // Tab change handler with lazy-loading
  const handleTabChange = async (key) => {
    setActiveTab(key);
    if (!id) return;

    if (key === 'training' && tabData.training === null && !tabLoading.training) {
      fetchTrainingRecords();
    } else if (key === 'outcomes' && tabData.outcomes === null && !tabLoading.outcomes) {
      fetchOutcomes();
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

  const handleAddTrainingRecord = async (values) => {
    setAddingRecord(true);
    setAddRecordError(null);

    const payload = {
      course_name: values.course_name?.trim(),
      provider_name: values.provider_name?.trim(),
      start_date: values.start_date.format('YYYY-MM-DD'),
      status: values.status,
    };

    if (values.program_name?.trim()) {
      payload.program_name = values.program_name.trim();
    }
    if (values.end_date) {
      payload.end_date = values.end_date.format('YYYY-MM-DD');
    }
    if (values.assessment_status) {
      payload.assessment_status = values.assessment_status;
    }
    if (typeof values.assessment_score === 'number') {
      payload.assessment_score = values.assessment_score;
    }
    if (typeof values.attendance_percentage === 'number') {
      payload.attendance_percentage = values.attendance_percentage;
    }
    if (values.certification_issued !== undefined) {
      payload.certification_issued = Boolean(values.certification_issued);
    }
    if (values.certification_issued && values.certification_id?.trim()) {
      payload.certification_id = values.certification_id.trim();
    }

    try {
      await api.post(`/api/trainees/${id}/training-records`, payload);
      message.success('Training record added successfully!');
      addRecordForm.resetFields();
      setAddRecordModalVisible(false);
      await fetchTrainingRecords();
    } catch (err) {
      if (err?.status === 422) {
        let msgText = 'Validation failed. Please check the fields below.';
        if (Array.isArray(err.detail)) {
          msgText = err.detail.map((e) => `${e.loc?.slice(1).join('.') || 'Field'}: ${e.msg}`).join(', ');
        } else if (typeof err.detail === 'string') {
          msgText = err.detail;
        }
        setAddRecordError(msgText);
      } else {
        setAddRecordError(
          (typeof err?.detail === 'string' ? err.detail : null) ||
          err?.message ||
          'Failed to add training record. Please try again.'
        );
      }
    } finally {
      setAddingRecord(false);
    }
  };

  const handleOpenAddOutcome = () => {
    setAddOutcomeError(null);
    addOutcomeForm.resetFields();
    if (!tabData.training || tabData.training.length === 0) {
      fetchTrainingRecords();
    }
    setAddOutcomeModalVisible(true);
  };

  const handleAddOutcome = async (values) => {
    setAddingOutcome(true);
    setAddOutcomeError(null);

    const outcomePayload = {
      trainee_id: id,
      training_id: values.training_id,
      outcome_type: values.outcome_type,
      status_date: values.status_date.format('YYYY-MM-DD'),
    };

    if (values.notes?.trim()) {
      outcomePayload.notes = values.notes.trim();
    }

    let outcomeRes = null;
    try {
      outcomeRes = await api.post('/api/outcomes', outcomePayload);
    } catch (err) {
      if (err?.status === 422) {
        let msgText = 'Validation failed. Please check the fields below.';
        if (Array.isArray(err.detail)) {
          msgText = err.detail.map((e) => `${e.loc?.slice(1).join('.') || 'Field'}: ${e.msg}`).join(', ');
        } else if (typeof err.detail === 'string') {
          msgText = err.detail;
        }
        setAddOutcomeError(msgText);
      } else {
        setAddOutcomeError(
          (typeof err?.detail === 'string' ? err.detail : null) ||
          err?.message ||
          'Failed to record outcome. Please try again.'
        );
      }
      setAddingOutcome(false);
      return;
    }

    // If Employed, proceed to create employment record
    if (values.outcome_type === 'Employed' && outcomeRes?.outcome_id) {
      let empStatus = values.employment_status || 'Active';
      if (empStatus === 'Left Job') empStatus = 'Left';

      let jobRel = values.job_relevance;
      if (jobRel === 'Somewhat Relevant') jobRel = 'Partially Relevant';

      const empPayload = {
        trainee_id: id,
        outcome_id: outcomeRes.outcome_id,
        company_name: values.company_name?.trim(),
        job_role: values.job_role?.trim(),
        joining_date: values.joining_date.format('YYYY-MM-DD'),
        salary: values.salary,
        employment_status: empStatus,
        job_relevance: jobRel,
      };

      if (values.job_location?.trim()) {
        empPayload.job_location = values.job_location.trim();
      }

      try {
        await api.post('/api/employment', empPayload);
        message.success('Outcome and employment details recorded successfully!');
      } catch (empErr) {
        const detailMsg =
          (typeof empErr?.detail === 'string' ? empErr.detail : null) ||
          empErr?.message ||
          'Failed to save employment details';
        message.warning(`Outcome recorded, but saving employment details failed: ${detailMsg}`);
      }
    } else {
      message.success('Outcome recorded successfully!');
    }

    addOutcomeForm.resetFields();
    setAddOutcomeModalVisible(false);
    setAddingOutcome(false);
    await fetchOutcomes();
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

  const trainingOptions = tabData.training || [];

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
      children: (
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              marginBottom: 16,
            }}
          >
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setAddRecordError(null);
                addRecordForm.resetFields();
                setAddRecordModalVisible(true);
              }}
            >
              Add Training Record
            </Button>
          </div>

          {tabLoading.training ? (
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
          )}
        </div>
      ),
    },
    {
      key: 'outcomes',
      label: 'Outcomes',
      children: (
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              marginBottom: 16,
            }}
          >
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleOpenAddOutcome}
            >
              Add Outcome
            </Button>
          </div>

          {tabLoading.outcomes ? (
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
          )}
        </div>
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

      {/* Add Training Record Modal */}
      <Modal
        title="Add Training Record"
        open={addRecordModalVisible}
        onCancel={() => {
          if (!addingRecord) {
            setAddRecordModalVisible(false);
          }
        }}
        footer={null}
        destroyOnClose
        width={640}
      >
        <div style={{ marginTop: 16 }}>
          {addRecordError && (
            <Alert
              type="error"
              message="Error Adding Training Record"
              description={addRecordError}
              showIcon
              closable
              onClose={() => setAddRecordError(null)}
              style={{ marginBottom: 20, borderRadius: 6 }}
            />
          )}

          <Form
            form={addRecordForm}
            layout="vertical"
            onFinish={handleAddTrainingRecord}
            initialValues={{
              status: 'Ongoing',
              assessment_status: undefined,
              certification_issued: false,
            }}
          >
            {/* Course Name */}
            <Form.Item
              label="Course Name"
              name="course_name"
              rules={[{ required: true, message: 'Please enter course name' }]}
            >
              <Input placeholder="e.g. Electrician Certification" />
            </Form.Item>

            {/* Provider Name */}
            <Form.Item
              label="Provider Name"
              name="provider_name"
              rules={[{ required: true, message: 'Please enter provider name' }]}
            >
              <Input placeholder="e.g. Apex Skill Center" />
            </Form.Item>

            {/* Program Name */}
            <Form.Item label="Program Name" name="program_name">
              <Input placeholder="e.g. PMKVY 4.0 (Optional)" />
            </Form.Item>

            {/* Dates: Start Date & End Date */}
            <Space style={{ display: 'flex' }} size={16}>
              <Form.Item
                label="Start Date"
                name="start_date"
                rules={[{ required: true, message: 'Please select start date' }]}
                style={{ flex: 1 }}
              >
                <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" placeholder="YYYY-MM-DD" />
              </Form.Item>

              <Form.Item
                label="End Date"
                name="end_date"
                style={{ flex: 1 }}
              >
                <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" placeholder="YYYY-MM-DD (Optional)" />
              </Form.Item>
            </Space>

            {/* Status & Assessment Status */}
            <Space style={{ display: 'flex' }} size={16}>
              <Form.Item
                label="Status"
                name="status"
                rules={[{ required: true, message: 'Please select status' }]}
                style={{ flex: 1 }}
              >
                <Select placeholder="Select status">
                  <Option value="Ongoing">Ongoing</Option>
                  <Option value="Completed">Completed</Option>
                  <Option value="Dropped">Dropped</Option>
                </Select>
              </Form.Item>

              <Form.Item
                label="Assessment Status"
                name="assessment_status"
                style={{ flex: 1 }}
              >
                <Select placeholder="Select assessment status" allowClear>
                  <Option value="Passed">Passed</Option>
                  <Option value="Failed">Failed</Option>
                  <Option value="Pending">Pending</Option>
                </Select>
              </Form.Item>
            </Space>

            {/* Assessment Score & Attendance Percentage */}
            <Space style={{ display: 'flex' }} size={16}>
              <Form.Item
                label="Assessment Score (%)"
                name="assessment_score"
                style={{ flex: 1 }}
              >
                <InputNumber min={0} max={100} style={{ width: '100%' }} placeholder="0 - 100" />
              </Form.Item>

              <Form.Item
                label="Attendance Percentage (%)"
                name="attendance_percentage"
                style={{ flex: 1 }}
              >
                <InputNumber min={0} max={100} style={{ width: '100%' }} placeholder="0 - 100" />
              </Form.Item>
            </Space>

            {/* Certification Issued */}
            <Form.Item
              label="Certification Issued"
              name="certification_issued"
              valuePropName="checked"
              style={{ marginBottom: 16 }}
            >
              <Switch checkedChildren="Yes" unCheckedChildren="No" />
            </Form.Item>

            {/* Certification ID */}
            {certIssued && (
              <Form.Item
                label="Certification ID"
                name="certification_id"
              >
                <Input placeholder="e.g. CERT-2025-9812" />
              </Form.Item>
            )}

            {/* Modal Actions */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 12,
                marginTop: 24,
              }}
            >
              <Button
                onClick={() => setAddRecordModalVisible(false)}
                disabled={addingRecord}
              >
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" loading={addingRecord}>
                Save Training Record
              </Button>
            </div>
          </Form>
        </div>
      </Modal>

      {/* Add Outcome Modal */}
      <Modal
        title="Add Outcome"
        open={addOutcomeModalVisible}
        onCancel={() => {
          if (!addingOutcome) {
            setAddOutcomeModalVisible(false);
          }
        }}
        footer={null}
        destroyOnClose
        width={680}
      >
        <div style={{ marginTop: 16 }}>
          {addOutcomeError && (
            <Alert
              type="error"
              message="Error Recording Outcome"
              description={addOutcomeError}
              showIcon
              closable
              onClose={() => setAddOutcomeError(null)}
              style={{ marginBottom: 20, borderRadius: 6 }}
            />
          )}

          <Form
            form={addOutcomeForm}
            layout="vertical"
            onFinish={handleAddOutcome}
            initialValues={{
              outcome_type: undefined,
              employment_status: 'Active',
              job_relevance: 'Relevant',
            }}
          >
            {/* Training Record Selector */}
            <Form.Item
              label="Training Record"
              name="training_id"
              rules={[{ required: true, message: 'Please select a training record' }]}
            >
              <Select
                placeholder={
                  trainingOptions.length > 0
                    ? 'Select a training record'
                    : 'Loading training records...'
                }
              >
                {trainingOptions.map((rec) => (
                  <Option key={rec.record_id} value={rec.record_id}>
                    {rec.course_name} ({rec.record_id}) — {rec.provider_name}
                  </Option>
                ))}
              </Select>
            </Form.Item>

            {/* Outcome Type */}
            <Form.Item
              label="Outcome Type"
              name="outcome_type"
              rules={[{ required: true, message: 'Please select outcome type' }]}
            >
              <Select placeholder="Select outcome type">
                <Option value="Employed">Employed</Option>
                <Option value="Self-employed">Self-employed</Option>
                <Option value="Apprenticeship">Apprenticeship</Option>
                <Option value="Unemployed">Unemployed</Option>
                <Option value="Further Education">Further Education</Option>
                <Option value="Not Reachable">Not Reachable</Option>
              </Select>
            </Form.Item>

            {/* Status Date */}
            <Form.Item
              label="Status Date"
              name="status_date"
              rules={[{ required: true, message: 'Please select status date' }]}
            >
              <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" placeholder="YYYY-MM-DD" />
            </Form.Item>

            {/* Notes */}
            <Form.Item label="Notes" name="notes">
              <Input.TextArea rows={2} placeholder="Additional outcome notes (optional)" />
            </Form.Item>

            {/* Dynamic Employment Fields if Employed */}
            {selectedOutcomeType === 'Employed' && (
              <div
                style={{
                  marginTop: 20,
                  marginBottom: 20,
                  padding: 20,
                  border: '1px solid #e8e8e8',
                  borderRadius: 8,
                  backgroundColor: '#fbfbfb',
                }}
              >
                <Title level={5} style={{ margin: '0 0 16px 0', fontWeight: 600 }}>
                  Employment Details
                </Title>

                <Form.Item
                  label="Company Name"
                  name="company_name"
                  rules={[{ required: true, message: 'Please enter company name' }]}
                >
                  <Input placeholder="e.g. Tata Consultancy Services" />
                </Form.Item>

                <Space style={{ display: 'flex' }} size={16}>
                  <Form.Item
                    label="Job Role"
                    name="job_role"
                    rules={[{ required: true, message: 'Please enter job role' }]}
                    style={{ flex: 1 }}
                  >
                    <Input placeholder="e.g. Electrician / Technician" />
                  </Form.Item>

                  <Form.Item
                    label="Job Location"
                    name="job_location"
                    style={{ flex: 1 }}
                  >
                    <Input placeholder="e.g. Mumbai (Optional)" />
                  </Form.Item>
                </Space>

                <Space style={{ display: 'flex' }} size={16}>
                  <Form.Item
                    label="Joining Date"
                    name="joining_date"
                    rules={[{ required: true, message: 'Please select joining date' }]}
                    style={{ flex: 1 }}
                  >
                    <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" placeholder="YYYY-MM-DD" />
                  </Form.Item>

                  <Form.Item
                    label="Monthly Salary (₹)"
                    name="salary"
                    rules={[{ required: true, message: 'Please enter salary' }]}
                    style={{ flex: 1 }}
                  >
                    <InputNumber min={0} style={{ width: '100%' }} placeholder="e.g. 18000" />
                  </Form.Item>
                </Space>

                <Space style={{ display: 'flex' }} size={16}>
                  <Form.Item
                    label="Employment Status"
                    name="employment_status"
                    rules={[{ required: true, message: 'Please select employment status' }]}
                    style={{ flex: 1 }}
                  >
                    <Select placeholder="Select status">
                      <Option value="Active">Active</Option>
                      <Option value="On Leave">On Leave</Option>
                      <Option value="Left Job">Left Job</Option>
                      <Option value="Terminated">Terminated</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item
                    label="Job Relevance"
                    name="job_relevance"
                    rules={[{ required: true, message: 'Please select job relevance' }]}
                    style={{ flex: 1 }}
                  >
                    <Select placeholder="Select relevance">
                      <Option value="Relevant">Relevant</Option>
                      <Option value="Somewhat Relevant">Somewhat Relevant</Option>
                      <Option value="Not Relevant">Not Relevant</Option>
                    </Select>
                  </Form.Item>
                </Space>
              </div>
            )}

            {/* Note for other outcome types */}
            {selectedOutcomeType && selectedOutcomeType !== 'Employed' && (
              <Alert
                type="info"
                icon={<InfoCircleOutlined />}
                message="Additional details for this outcome type coming soon"
                showIcon
                style={{ marginTop: 12, marginBottom: 16, borderRadius: 6 }}
              />
            )}

            {/* Modal Actions */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 12,
                marginTop: 24,
              }}
            >
              <Button
                onClick={() => setAddOutcomeModalVisible(false)}
                disabled={addingOutcome}
              >
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" loading={addingOutcome}>
                Save Outcome
              </Button>
            </div>
          </Form>
        </div>
      </Modal>
    </div>
  );
}
