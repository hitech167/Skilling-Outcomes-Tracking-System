import { useState } from 'react';
import { Modal, Form, Input, Alert, Button, Descriptions, Tag, Typography, message } from 'antd';
import { api, errorMessage } from '../api/client';

const { Text, Paragraph } = Typography;

const DELIVERY_COLORS = { Sent: 'green', Queued: 'gold', Failed: 'red' };

/**
 * Sends an employer a new confirmation link for one job
 * (POST /api/employment/{id}/verification-request). The link is emailed when
 * the contact is an email and SMTP is set up; otherwise staff can copy it.
 */
export default function SendVerificationModal({ open, employment, defaultContact, onClose, onSent }) {
  const [form] = Form.useForm();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const handleSend = async ({ employer_contact }) => {
    setSending(true);
    setError(null);
    try {
      const contact = employer_contact?.trim();
      const res = await api.post(
        `/api/employment/${encodeURIComponent(employment.employment_id)}/verification-request`,
        contact ? { employer_contact: contact } : {}
      );
      setResult(res);
      message.success(`Verification request ${res.verification_id} created.`);
      onSent?.(res);
    } catch (err) {
      setError(errorMessage(err, 'Failed to create the verification request.'));
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal
      title="Send to employer"
      open={open}
      onCancel={() => !sending && onClose()}
      afterClose={() => {
        setError(null);
        setResult(null);
      }}
      footer={
        result
          ? [
              <Button key="done" type="primary" onClick={onClose}>
                Done
              </Button>,
            ]
          : [
              <Button key="cancel" onClick={onClose} disabled={sending}>
                Cancel
              </Button>,
              <Button key="send" type="primary" loading={sending} onClick={() => form.submit()}>
                Send request
              </Button>,
            ]
      }
      destroyOnHidden
    >
      {employment && (
        <Paragraph type="secondary" style={{ marginTop: 8 }}>
          Ask <Text strong>{employment.company_name || 'the employer'}</Text> to confirm{' '}
          {employment.job_role ? <Text strong>{employment.job_role}</Text> : 'this job'} (
          <Text code>{employment.employment_id}</Text>). A new Pending verification is created;
          earlier ones are kept as history.
        </Paragraph>
      )}

      {error && (
        <Alert type="error" showIcon message={error} style={{ marginBottom: 16, borderRadius: 6 }} />
      )}

      {result ? (
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Verification ID">{result.verification_id}</Descriptions.Item>
          <Descriptions.Item label="Delivery">
            {result.delivery_status ? (
              <Tag color={DELIVERY_COLORS[result.delivery_status] || 'default'}>
                {result.delivery_status}
              </Tag>
            ) : (
              <Text type="secondary">No contact given — share the link yourself</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Confirmation link">
            <Text copyable style={{ wordBreak: 'break-all' }}>
              {result.link}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label="Valid for">{result.valid_days} days</Descriptions.Item>
        </Descriptions>
      ) : (
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSend}
          initialValues={{ employer_contact: defaultContact || '' }}
        >
          <Form.Item
            label="Employer contact"
            name="employer_contact"
            rules={[{ max: 255, message: 'Contact must be at most 255 characters' }]}
            extra="An email is sent the link automatically; a phone number gets an SMS if SMS is set up. Leave blank to copy the link yourself."
          >
            <Input placeholder="e.g. hr@company.com or 9876543210" />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}
