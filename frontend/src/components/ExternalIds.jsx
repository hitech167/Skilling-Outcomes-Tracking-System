import { useEffect, useState } from 'react';
import { Table, Form, Input, AutoComplete, Button, Alert, Spin, Typography, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import { ID_TYPE_OPTIONS, idTypeRules, idValueRules, filterIdType } from '../constants/identity';

const { Text } = Typography;

const COLUMNS = [
  { title: 'ID type', dataIndex: 'id_type', key: 'id_type' },
  {
    title: 'ID value',
    dataIndex: 'id_value',
    key: 'id_value',
    render: (val) => <Text code copyable>{val}</Text>,
  },
  {
    title: 'Source programme',
    dataIndex: 'source_programme',
    key: 'source_programme',
    render: (val) => val || '—',
  },
];

/**
 * External IDs (Skill India Digital ID, PMKVY / DDU-GKY candidate IDs, state
 * scheme numbers...) linked to one trainee, with a form to link another.
 */
export default function ExternalIds({ traineeId }) {
  const [ids, setIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [form] = Form.useForm();

  useEffect(() => {
    let isMounted = true;

    async function fetchIds() {
      try {
        const data = await api.get(`/api/trainees/${encodeURIComponent(traineeId)}/external-ids`);
        if (isMounted) {
          setIds(Array.isArray(data) ? data : []);
          setLoadError(null);
        }
      } catch (err) {
        if (isMounted) setLoadError(err?.detail || 'Failed to load external IDs.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchIds();

    return () => {
      isMounted = false;
    };
  }, [traineeId]);

  const handleAdd = async (values) => {
    setSaving(true);
    setSaveError(null);
    try {
      const created = await api.post(`/api/trainees/${encodeURIComponent(traineeId)}/external-ids`, {
        id_type: values.id_type.trim(),
        id_value: values.id_value.trim(),
        source_programme: values.source_programme?.trim() || null,
      });
      // Re-linking an ID the trainee already has is a no-op on the backend
      setIds((prev) =>
        prev.some(
          (i) =>
            i.id_type.toLowerCase() === created.id_type.toLowerCase() && i.id_value === created.id_value
        )
          ? prev
          : [...prev, created]
      );
      form.resetFields();
      message.success('External ID linked');
    } catch (err) {
      const detail = err?.detail;
      setSaveError(
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
          ? detail.map((d) => d.msg).join('; ')
          : 'Failed to link external ID.'
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '32px 0' }}>
        <Spin />
      </div>
    );
  }

  return (
    <>
      {loadError ? (
        <Alert type="error" showIcon message={loadError} style={{ marginBottom: 16 }} />
      ) : (
        <Table
          rowKey={(r) => `${r.id_type}:${r.id_value}`}
          columns={COLUMNS}
          dataSource={ids}
          locale={{ emptyText: 'No external IDs linked yet' }}
          pagination={false}
          size="middle"
          scroll={{ x: true }}
          style={{ marginBottom: 20 }}
        />
      )}

      <Text strong style={{ display: 'block', marginBottom: 8 }}>
        Link an external ID
      </Text>
      {saveError && (
        <Alert
          type="error"
          showIcon
          closable
          onClose={() => setSaveError(null)}
          message={saveError}
          style={{ marginBottom: 12 }}
        />
      )}
      <Form form={form} layout="inline" onFinish={handleAdd} style={{ rowGap: 12 }}>
        <Form.Item name="id_type" rules={idTypeRules} style={{ minWidth: 220 }}>
          <AutoComplete options={ID_TYPE_OPTIONS} placeholder="ID type" filterOption={filterIdType} />
        </Form.Item>
        <Form.Item name="id_value" rules={idValueRules} style={{ minWidth: 180 }}>
          <Input placeholder="ID value" />
        </Form.Item>
        <Form.Item name="source_programme" rules={[{ max: 200 }]} style={{ minWidth: 180 }}>
          <Input placeholder="Source programme (optional)" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" icon={<PlusOutlined />} loading={saving}>
            Link ID
          </Button>
        </Form.Item>
      </Form>
      <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
        Do not record Aadhaar numbers. An ID already linked to another trainee is rejected.
      </Text>
    </>
  );
}
