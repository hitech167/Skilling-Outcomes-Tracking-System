import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Form, Input, Button, Alert, Typography, Divider, Space } from 'antd';
import { motion } from 'framer-motion';
import { errorMessage as describeError, login } from '../api/client';

const { Title, Text } = Typography;

// SIH judging: lets reviewers explore the app without being handed real
// credentials out-of-band. These are dedicated public demo credentials
// (set via ADMIN_PASSWORD / ANALYST_PASSWORD on the backend) sitting on
// fake/test data only — never point this at a deployment with real
// trainee data.
const DEMO_ACCOUNTS = {
  admin: { username: 'admin', password: 'demo-admin-sih2026' },
  analyst: { username: 'analyst', password: 'demo-analyst-sih2026' },
};

export default function Login() {
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Login — Skilling Outcomes Tracking System";
  }, []);

  const doLogin = async (username, password) => {
    setErrorMessage('');
    try {
      await login(username, password);
      navigate('/dashboard');
    } catch (err) {
      // login() throws { status, detail }; there is no err.message to read
      setErrorMessage(describeError(err, 'Login failed. Please check your credentials.'));
    }
  };

  const handleSubmit = async (values) => {
    setLoading(true);
    await doLogin(values.username, values.password);
    setLoading(false);
  };

  const handleDemoLogin = async (role) => {
    setDemoLoading(role);
    const { username, password } = DEMO_ACCOUNTS[role];
    await doLogin(username, password);
    setDemoLoading(null);
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: '#f5f7fa',
        padding: '24px',
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        style={{ width: '100%', maxWidth: 400 }}
      >
        <Card
          style={{
            borderRadius: 12,
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.05)',
            border: '1px solid #eef0f3',
          }}
          styles={{ body: { padding: '32px 24px' } }}
        >
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
              Welcome Back
            </Title>
            <Text type="secondary" style={{ fontSize: 14 }}>
              Sign in to your account
            </Text>
          </div>

          {errorMessage && (
            <Alert
              message={errorMessage}
              type="error"
              showIcon
              closable
              onClose={() => setErrorMessage('')}
              style={{ marginBottom: 20 }}
            />
          )}

          <Form
            name="login"
            layout="vertical"
            onFinish={handleSubmit}
            autoComplete="off"
            requiredMark={false}
          >
            <Form.Item
              label="Username"
              name="username"
              rules={[{ required: true, message: 'Please enter your username' }]}
            >
              <Input placeholder="Enter your username" size="large" />
            </Form.Item>

            <Form.Item
              label="Password"
              name="password"
              rules={[{ required: true, message: 'Please enter your password' }]}
            >
              <Input.Password placeholder="Enter your password" size="large" />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                block
                loading={loading}
                disabled={demoLoading !== null}
              >
                Sign In
              </Button>
            </Form.Item>
          </Form>

          <Divider style={{ margin: '20px 0 16px' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              For SIH reviewers
            </Text>
          </Divider>

          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Button
              block
              loading={demoLoading === 'admin'}
              disabled={loading || (demoLoading !== null && demoLoading !== 'admin')}
              onClick={() => handleDemoLogin('admin')}
            >
              View Demo — Admin
            </Button>
            <Button
              block
              loading={demoLoading === 'analyst'}
              disabled={loading || (demoLoading !== null && demoLoading !== 'analyst')}
              onClick={() => handleDemoLogin('analyst')}
            >
              View Demo — Analyst
            </Button>
          </Space>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', textAlign: 'center', marginTop: 10 }}>
            Demo accounts, fake/test data only — no real trainee information.
          </Text>
        </Card>

        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <a href="/impact" style={{ fontSize: 13, color: '#8c8c8c' }}>
            View the public programme impact page →
          </a>
        </div>
      </motion.div>
    </div>
  );
}
