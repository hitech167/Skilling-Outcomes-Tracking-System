import { useState } from 'react';
import {
  Card,
  Form,
  Input,
  DatePicker,
  Select,
  Checkbox,
  Button,
  Alert,
  Typography,
  Space,
  message,
} from 'antd';
import { CopyOutlined, CheckCircleOutlined, WarningOutlined } from '@ant-design/icons';
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

export default function RegisterTrainee() {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [successResult, setSuccessResult] = useState(null);
  const [errorState, setErrorState] = useState(null);

  const handleSubmit = async (values) => {
    setSubmitting(true);
    setErrorState(null);
    setSuccessResult(null);

    const payload = {
      full_name: values.full_name?.trim(),
      dob: values.dob ? values.dob.format('YYYY-MM-DD') : '',
      gender: values.gender,
      district: values.district?.trim(),
      current_location: values.current_location?.trim() || null,
      phone: values.phone?.trim(),
      email: values.email?.trim() || null,
      preferred_contact: values.preferred_contact,
      consent_given: Boolean(values.consent_given),
      consent_method: values.consent_method || null,
      consent_recorded_by: values.consent_recorded_by?.trim() || null,
    };

    try {
      const response = await api.post('/api/trainees', payload);
      const profileLink =
        response?.profile_link ||
        `${window.location.origin}/trainees/${response.trainee_id}`;

      setSuccessResult({
        trainee_id: response.trainee_id,
        profile_link: profileLink,
        possible_duplicates: response.possible_duplicates || [],
      });

      updateRecentTrainees(response.trainee_id, values.full_name?.trim());

      form.resetFields();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      if (err?.status === 422) {
        let msgText = 'Validation failed. Please check the fields below.';
        if (Array.isArray(err.detail)) {
          msgText = err.detail.map((e) => `${e.loc?.slice(1).join('.') || 'Field'}: ${e.msg}`).join(', ');
        } else if (typeof err.detail === 'string') {
          msgText = err.detail;
        }
        setErrorState({
          type: 'error',
          title: 'Validation Error (422)',
          message: msgText,
        });
      } else if (err?.status === 409) {
        setErrorState({
          type: 'error',
          title: 'Conflict Error (409)',
          message: typeof err.detail === 'string' ? err.detail : 'A trainee with this contact number or ID already exists.',
        });
      } else {
        setErrorState({
          type: 'error',
          title: 'Registration Error',
          message:
            (typeof err?.detail === 'string' ? err.detail : null) ||
            err?.message ||
            'Failed to register trainee. Please try again later.',
        });
      }
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setSubmitting(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    message.success('Trainee profile link copied to clipboard!');
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Register Trainee
        </Title>
        <Text type="secondary">
          Enter candidate demographics, contact preferences, and recorded consent details.
        </Text>
      </div>

      {/* Success Notification Banner */}
      {successResult && (
        <div style={{ marginBottom: 24 }}>
          <Alert
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
            message={
              <Space orientation="vertical" size={4} style={{ width: '100%' }}>
                <Text strong style={{ fontSize: 15, color: '#277024' }}>
                  Registered as {successResult.trainee_id} · Trainee link:
                </Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <Text orientation="horizontal" code style={{ fontSize: 13, wordBreak: 'break-all' }}>
                    {successResult.profile_link}
                  </Text>
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => copyToClipboard(successResult.profile_link)}
                  >
                    Copy
                  </Button>
                </div>
              </Space>
            }
            style={{ borderRadius: 8, padding: '16px 20px', border: '1px solid #b7eb8f' }}
          />

          {/* Warning for Possible Duplicates */}
          {successResult.possible_duplicates && successResult.possible_duplicates.length > 0 && (
            <Alert
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              message="Possible Duplicate Warning"
              description={
                <div>
                  <Paragraph style={{ margin: '0 0 8px 0', fontSize: 13 }}>
                    The following existing trainees share the same name and date of birth:
                  </Paragraph>
                  <ul style={{ paddingLeft: 20, margin: 0, fontSize: 13 }}>
                    {successResult.possible_duplicates.map((dupId, idx) => (
                      <li key={idx}>
                        <Text strong>{dupId}</Text>
                      </li>
                    ))}
                  </ul>
                </div>
              }
              style={{ marginTop: 12, borderRadius: 8 }}
            />
          )}
        </div>
      )}

      {/* Error Alert */}
      {errorState && (
        <Alert
          type={errorState.type}
          message={errorState.title}
          description={errorState.message}
          showIcon
          closable
          onClose={() => setErrorState(null)}
          style={{ marginBottom: 24, borderRadius: 8 }}
        />
      )}

      {/* Main Registration Form Card */}
      <Card
        style={{
          borderRadius: 12,
          border: '1px solid #eef0f3',
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
        }}
        styles={{ body: { padding: '32px' } }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          requiredMark="optional"
          initialValues={{
            gender: 'Male',
            preferred_contact: 'Phone',
            consent_method: 'Digital form',
            consent_given: false,
          }}
        >
          {/* 1. Full name */}
          <Form.Item
            label="Full name"
            name="full_name"
            rules={[
              { required: true, message: 'Please enter the trainee full name' },
              { min: 2, message: 'Name must be at least 2 characters' },
            ]}
          >
            <Input placeholder="e.g. Rahul Patil" size="large" />
          </Form.Item>

          {/* 2. Date of birth */}
          <Form.Item
            label="Date of birth"
            name="dob"
            rules={[{ required: true, message: 'Please select date of birth' }]}
          >
            <DatePicker
              style={{ width: '100%' }}
              size="large"
              format="YYYY-MM-DD"
              placeholder="YYYY-MM-DD"
            />
          </Form.Item>

          {/* 3. Gender */}
          <Form.Item
            label="Gender"
            name="gender"
            rules={[{ required: true, message: 'Please select gender' }]}
          >
            <Select size="large" placeholder="Select gender">
              <Option value="Male">Male</Option>
              <Option value="Female">Female</Option>
              <Option value="Other">Other</Option>
            </Select>
          </Form.Item>

          {/* 4. Mobile number */}
          <Form.Item
            label="Mobile number"
            name="phone"
            rules={[
              { required: true, message: 'Please enter mobile number' },
              {
                pattern: /^[6-9]\d{9}$/,
                message: 'Enter a valid 10-digit mobile number starting with 6-9',
              },
            ]}
          >
            <Input placeholder="e.g. 9876543210" size="large" maxLength={10} />
          </Form.Item>

          {/* 5. District */}
          <Form.Item
            label="District"
            name="district"
            rules={[{ required: true, message: 'Please enter district' }]}
          >
            <Input placeholder="e.g. Raigad" size="large" />
          </Form.Item>

          {/* 6. Town / area */}
          <Form.Item
            label="Town / area"
            name="current_location"
          >
            <Input placeholder="e.g. Panvel" size="large" />
          </Form.Item>

          {/* 7. Email */}
          <Form.Item
            label="Email"
            name="email"
            rules={[{ type: 'email', message: 'Please enter a valid email address' }]}
          >
            <Input placeholder="e.g. rahul.patil@example.com" size="large" />
          </Form.Item>

          {/* 8. Contact by */}
          <Form.Item
            label="Contact by"
            name="preferred_contact"
            rules={[{ required: true, message: 'Please select preferred contact method' }]}
          >
            <Select size="large" placeholder="Select preferred contact method">
              <Option value="SMS">SMS</Option>
              <Option value="Email">Email</Option>
              <Option value="Phone">Phone</Option>
            </Select>
          </Form.Item>

          {/* 9. Bordered Consent Section */}
          <div
            style={{
              marginTop: 28,
              marginBottom: 28,
              padding: '24px',
              border: '1px solid #d9d9d9',
              borderRadius: 8,
              backgroundColor: '#fafafa',
            }}
          >
            <Title level={5} style={{ margin: '0 0 16px 0', fontWeight: 600 }}>
              Consent
            </Title>

            <Form.Item
              name="consent_given"
              valuePropName="checked"
              rules={[
                {
                  validator: (_, value) =>
                    value
                      ? Promise.resolve()
                      : Promise.reject(
                          new Error(
                            'The trainee must agree to follow-up contact and data usage to proceed'
                          )
                        ),
                },
              ]}
              style={{ marginBottom: 20 }}
            >
              <Checkbox>
                <Text style={{ fontSize: 13, lineHeight: 1.5 }}>
                  The trainee agrees to follow-up contact and to their data being used for
                  anonymous statistics <Text type="danger">*</Text>
                </Text>
              </Checkbox>
            </Form.Item>

            <Form.Item
              label="How was it taken"
              name="consent_method"
              style={{ marginBottom: 16 }}
            >
              <Select size="large" placeholder="Select consent method">
                <Option value="Paper form">Paper form</Option>
                <Option value="Digital form">Digital form</Option>
                <Option value="Verbal">Verbal</Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="Recorded by"
              name="consent_recorded_by"
              style={{ marginBottom: 0 }}
            >
              <Input placeholder="Staff member name / ID" size="large" />
            </Form.Item>
          </div>

          {/* 10. Submit button */}
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              loading={submitting}
              style={{ width: '100%', height: 44, fontWeight: 500 }}
            >
              Register trainee
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
