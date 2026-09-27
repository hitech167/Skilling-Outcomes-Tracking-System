import { useEffect, useState } from 'react';
import {
  Modal,
  Table,
  Tag,
  Form,
  Select,
  DatePicker,
  Input,
  Button,
  Alert,
  Space,
  Typography,
  message,
} from 'antd';
import { api, errorMessage } from '../api/client';
import { RETENTION_STATUSES, RETENTION_STATUS_COLORS } from '../constants/employment';

const { Text, Title } = Typography;

const HISTORY_COLUMNS = [
  { title: 'Date', dataIndex: 'status_date', key: 'status_date', width: 120 },
  {
    title: 'Status',
    dataIndex: 'employment_status',
    key: 'employment_status',
    render: (st) => <Tag color={RETENTION_STATUS_COLORS[st] || 'default'}>{st}</Tag>,
  },
  { title: 'Reason', dataIndex: 'reason', key: 'reason', render: (v) => v || '—' },
  { title: 'Notes', dataIndex: 'notes', key: 'notes', render: (v) => v || '—' },
];

/**
 * Job retention for one employment: its status history (oldest first, never
 * edited) and a form to record the next change, e.g. "Left Job".
 */
export default function EmploymentStatusModal({ open, traineeId, employment, onClose, onRecorded }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [form] = Form.useForm();

  const employmentId = employment?.employment_id;

  useEffect(() => {
    if (!open || !employmentId) return;
    let isMounted = true;

    async function fetchHistory() {
      setLoading(true);
      setLoadError(null);
      setSaveError(null);
      form.resetFields();
      try {
        const res = await api.get(`/api/employment/${encodeURIComponent(employmentId)}/status-history`);
        if (isMounted) setHistory(res?.status_history || []);
      } catch (err) {
        if (isMounted) setLoadError(errorMessage(err, 'Failed to load the status history.'));
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchHistory();

    return () => {
      isMounted = false;
    };
  }, [open, employmentId, form]);

  const handleRecord = async (values) => {
    setSaving(true);
    setSaveError(null);
    const payload = {
      trainee_id: traineeId,
      employment_id: employmentId,
      employment_status: values.employment_status,
      status_date: values.status_date.format('YYYY-MM-DD'),
    };
    if (values.reason?.trim()) payload.reason = values.reason.trim();
    if (values.notes?.trim()) payload.notes = values.notes.trim();

    try {
      const created = await api.post('/api/employment-status', payload);
      // History is ordered by status date, and a back-dated change can land mid-list
      setHistory((prev) =>
        [...prev, created].sort((a, b) => a.status_date.localeCompare(b.status_date))
      );
      form.resetFields();
      message.success(`Status "${created.employment_status}" recorded.`);
      onRecorded?.();
    } catch (err) {
      setSaveError(errorMessage(err, 'Failed to record the status change.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={
        employment ? `Job status — ${employment.company_name} (${employment.job_role})` : 'Job status'
      }
      open={open}
      onCancel={() => !saving && onClose()}
      footer={[
        <Button key="close" onClick={onClose} disabled={saving}>
          Close
        </Button>,
      ]}
      destroyOnHidden
      width={720}
    >
      <Title level={5} style={{ marginTop: 8 }}>
        Status history
      </Title>
      {loadError ? (
        <Alert type="error" showIcon message={loadError} style={{ marginBottom: 16 }} />
      ) : (
        <Table
          rowKey="status_record_id"
          columns={HISTORY_COLUMNS}
          dataSource={history}
          loading={loading}
          size="small"
          pagination={false}
          locale={{
            emptyText: `No changes recorded yet — status at joining: ${
              employment?.current_status || 'unknown'
            }`,
          }}
          scroll={{ x: true }}
          style={{ marginBottom: 24 }}
        />
      )}

      <div
        style={{
          padding: 20,
          border: '1px solid #e8e8e8',
          borderRadius: 8,
          backgroundColor: '#fbfbfb',
        }}
      >
        <Title level={5} style={{ margin: '0 0 16px 0', fontWeight: 600 }}>
          Record a status change
        </Title>

        {saveError && (
          <Alert
            type="error"
            showIcon
            message={saveError}
            closable
            onClose={() => setSaveError(null)}
            style={{ marginBottom: 16, borderRadius: 6 }}
          />
        )}

        <Form form={form} layout="vertical" onFinish={handleRecord}>
          <Space style={{ display: 'flex' }} size={16}>
            <Form.Item
              label="New Status"
              name="employment_status"
              rules={[{ required: true, message: 'Please select a status' }]}
              style={{ flex: 1 }}
            >
              <Select placeholder="Select status">
                {RETENTION_STATUSES.map((st) => (
                  <Select.Option key={st} value={st}>
                    {st}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>

            <Form.Item
              label="Effective Date"
              name="status_date"
              rules={[{ required: true, message: 'Please select a date' }]}
              style={{ flex: 1 }}
            >
              <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" placeholder="YYYY-MM-DD" />
            </Form.Item>
          </Space>

          <Form.Item label="Reason" name="reason" rules={[{ max: 150 }]}>
            <Input placeholder="e.g. Better job opportunity (Optional)" />
          </Form.Item>

          <Form.Item label="Notes" name="notes">
            <Input.TextArea rows={2} placeholder="Optional" />
          </Form.Item>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Earlier entries are kept — each change adds to the retention timeline.
            </Text>
            <Button type="primary" htmlType="submit" loading={saving}>
              Record Status
            </Button>
          </div>
        </Form>
      </div>
    </Modal>
  );
}
