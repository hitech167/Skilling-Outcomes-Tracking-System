import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Card, Input, Button, List, Typography, Alert, Space } from 'antd';
import { SearchOutlined, UserAddOutlined, HistoryOutlined, RightOutlined } from '@ant-design/icons';
import { api } from '../api/client';

const { Title, Text } = Typography;

export default function Trainees() {
  const [searchId, setSearchId] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [recentTrainees, setRecentTrainees] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Trainee Lookup — Skilling Outcomes Tracking System";
    try {
      const raw = sessionStorage.getItem('recentTrainees');
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setRecentTrainees(parsed);
        }
      }
    } catch (e) {
      console.error('Failed to read recent trainees from sessionStorage', e);
    }
  }, []);

  const handleSearch = async () => {
    const trimmedId = searchId.trim().toUpperCase();
    if (!trimmedId) {
      setErrorMessage('Please enter a valid Trainee ID');
      return;
    }

    setLoading(true);
    setErrorMessage('');

    try {
      await api.get(`/api/trainees/${trimmedId}`);
      navigate(`/trainees/${trimmedId}`);
    } catch (err) {
      setErrorMessage('No trainee found with that ID');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      {/* Header bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
            Trainee Lookup
          </Title>
          <Text type="secondary">
            Search for an individual trainee by their system-generated ID.
          </Text>
        </div>

        <Link to="/trainees/register">
          <Button type="primary" icon={<UserAddOutlined />} size="middle">
            + Register new trainee
          </Button>
        </Link>
      </div>

      {/* Search Box Card */}
      <Card
        style={{
          borderRadius: 12,
          border: '1px solid #eef0f3',
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
          marginBottom: 28,
        }}
        styles={{ body: { padding: '28px' } }}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 14 }}>
              Enter Trainee ID (e.g. TRN000207)
            </Text>
            <Space orientation="horizontal" style={{ width: '100%' }}>
              <Input
                size="large"
                placeholder="TRN000001"
                value={searchId}
                onChange={(e) => {
                  setSearchId(e.target.value);
                  if (errorMessage) setErrorMessage('');
                }}
                onPressEnter={handleSearch}
                style={{ minWidth: 280, maxWidth: 450 }}
                prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
              />
              <Button
                type="primary"
                size="large"
                loading={loading}
                onClick={handleSearch}
              >
                Search
              </Button>
            </Space>
          </div>

          {errorMessage && (
            <Alert
              type="error"
              message={errorMessage}
              showIcon
              closable
              onClose={() => setErrorMessage('')}
              style={{ borderRadius: 6 }}
            />
          )}
        </Space>
      </Card>

      {/* Recently Viewed Section */}
      <Card
        title={
          <Space>
            <HistoryOutlined style={{ color: '#1677ff' }} />
            <span>Recently Viewed Trainees</span>
          </Space>
        }
        style={{
          borderRadius: 12,
          border: '1px solid #eef0f3',
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
        }}
        styles={{ body: { padding: '16px 24px' } }}
      >
        {recentTrainees.length > 0 ? (
          <List
            itemLayout="horizontal"
            dataSource={recentTrainees}
            renderItem={(item) => (
              <List.Item
                style={{
                  cursor: 'pointer',
                  padding: '12px 16px',
                  borderRadius: 6,
                  transition: 'background-color 0.2s',
                }}
                className="recent-trainee-item"
                onClick={() => navigate(`/trainees/${item.trainee_id}`)}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{item.full_name}</Text>
                      <Text type="secondary" code>
                        {item.trainee_id}
                      </Text>
                    </Space>
                  }
                />
                <RightOutlined style={{ color: '#bfbfbf', fontSize: 12 }} />
              </List.Item>
            )}
          />
        ) : (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <Text type="secondary" style={{ fontSize: 14 }}>
              No trainees viewed yet — search above or register a new one
            </Text>
          </div>
        )}
      </Card>
    </div>
  );
}
