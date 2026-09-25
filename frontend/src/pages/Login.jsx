import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Form, Input, Button, Alert, Typography } from 'antd';
import { motion } from 'framer-motion';
import { login } from '../api/client';

const { Title, Text } = Typography;
export default function Login() {
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Login — Skilling Outcomes Tracking System";
  }, []);

  const handleSubmit = async (values) => {
    setLoading(true);
    setErrorMessage('');

    try {
      await login(values.username, values.password);
      navigate('/dashboard');
    } catch (err) {
      setErrorMessage(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
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
              >
                Sign In
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </motion.div>
    </div>
  );
}
