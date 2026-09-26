import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Card,
  Table,
  Tag,
  Button,
  Typography,
  Segmented,
  Popconfirm,
  Tooltip,
  Alert,
  Empty,
  message,
} from 'antd';
import {
  CheckOutlined,
  ReloadOutlined,
  MailOutlined,
  MessageOutlined,
  PhoneOutlined,
  WhatsAppOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const { Title, Text, Paragraph } = Typography;

const STATUS_FILTERS = ['Queued', 'Sent', 'Failed', 'All'];

const STATUS_COLORS = {
  Queued: 'gold',
  Sent: 'green',
  Failed: 'red',
};

const CHANNEL_ICONS = {
  Email: <MailOutlined />,
  SMS: <MessageOutlined />,
  Phone: <PhoneOutlined />,
  WhatsApp: <WhatsAppOutlined />,
};

const PURPOSE_LABELS = {
  FOLLOWUP_REQUEST: { label: 'Follow-up', color: 'blue' },
  FOLLOWUP_ATTEMPT: { label: 'Follow-up attempt', color: 'geekblue' },
  EMPLOYER_VERIFICATION: { label: 'Employer verification', color: 'purple' },
  PROFILE_LINK: { label: 'Profile link', color: 'cyan' },
  PHONE_VERIFICATION: { label: 'Phone verification', color: 'magenta' },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: 'easeOut' },
  },
};

const cardStyle = {
  borderRadius: 12,
  border: '1px solid #eef0f3',
  boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
};

function formatDateTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

export default function Messages() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('Queued');
  const [reloadKey, setReloadKey] = useState(0);
  const [markingId, setMarkingId] = useState(null);

  useEffect(() => {
    document.title = 'Messages — Skilling Outcomes Tracking System';
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function fetchNotifications() {
      const query = statusFilter === 'All' ? '' : `&status=${statusFilter}`;
      try {
        const data = await api.get(`/api/notifications?limit=500${query}`);
        if (isMounted) {
          setNotifications(Array.isArray(data) ? data : []);
          setLoadError(null);
        }
      } catch (err) {
        if (isMounted) setLoadError(err?.detail || 'Failed to load messages.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchNotifications();

    return () => {
      isMounted = false;
    };
  }, [statusFilter, reloadKey]);

  const reload = useCallback(() => {
    setLoading(true);
    setReloadKey((k) => k + 1);
  }, []);

  const handleFilterChange = (value) => {
    setLoading(true);
    setStatusFilter(value);
  };

  const handleMarkSent = async (notificationId) => {
    setMarkingId(notificationId);
    try {
      const updated = await api.post(
        `/api/notifications/${encodeURIComponent(notificationId)}/mark-sent`
      );
      message.success(`${notificationId} marked as sent`);
      setNotifications((prev) =>
        statusFilter === 'All' || statusFilter === 'Sent'
          ? prev.map((n) => (n.notification_id === notificationId ? updated : n))
          : prev.filter((n) => n.notification_id !== notificationId)
      );
    } catch (err) {
      message.error(err?.detail || 'Failed to mark message as sent');
    } finally {
      setMarkingId(null);
    }
  };

  const columns = [
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: formatDateTime,
    },
    {
      title: 'Trainee',
      key: 'trainee',
      width: 180,
      render: (_, row) => (
        <Link to={`/trainees/${row.trainee_id}`}>{row.trainee_name || row.trainee_id}</Link>
      ),
    },
    {
      title: 'Purpose',
      dataIndex: 'purpose',
      key: 'purpose',
      width: 170,
      render: (purpose) => {
        const p = PURPOSE_LABELS[purpose];
        return <Tag color={p?.color || 'default'}>{p?.label || purpose}</Tag>;
      },
    },
    {
      title: 'Channel',
      key: 'channel',
      width: 220,
      render: (_, row) => (
        <div>
          <Tag icon={CHANNEL_ICONS[row.channel]} color="cyan">
            {row.channel}
          </Tag>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }} copyable>
              {row.recipient}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: 'Message',
      dataIndex: 'message',
      key: 'message',
      render: (text) => (
        <Paragraph
          style={{ margin: 0, fontSize: 13, minWidth: 260, maxWidth: 420 }}
          ellipsis={{ rows: 2, expandable: true, symbol: 'more' }}
        >
          {text}
        </Paragraph>
      ),
    },
    {
      title: 'Status',
      key: 'status',
      width: 150,
      render: (_, row) => (
        <div>
          <Tag color={STATUS_COLORS[row.status] || 'default'}>{row.status}</Tag>
          {row.error && row.status !== 'Sent' && (
            <Tooltip title={row.error}>
              <WarningOutlined style={{ color: '#d46b08' }} />
            </Tooltip>
          )}
          {row.sent_at && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {formatDateTime(row.sent_at)}
                {row.provider ? ` · ${row.provider}` : ''}
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: 'Action',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_, row) =>
        row.status === 'Sent' ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            —
          </Text>
        ) : (
          <Popconfirm
            title="Mark as sent?"
            description="Confirm you have sent this message or called the recipient."
            okText="Mark sent"
            onConfirm={() => handleMarkSent(row.notification_id)}
          >
            <Button
              size="small"
              icon={<CheckOutlined />}
              loading={markingId === row.notification_id}
            >
              Mark sent
            </Button>
          </Popconfirm>
        ),
    },
  ];

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div
        style={{
          marginBottom: 28,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          flexWrap: 'wrap',
          gap: 16,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
            Messages
          </Title>
          <Text type="secondary" style={{ fontSize: 14 }}>
            Outbox of automated follow-up and verification messages. Queued messages are waiting
            for a delivery provider or a staff member to send or call.
          </Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={reload} disabled={loading}>
          Refresh
        </Button>
      </div>

      <motion.div variants={itemVariants} initial="hidden" animate="visible">
        <Card
          style={cardStyle}
          title="Notification outbox"
          extra={
            <Segmented
              value={statusFilter}
              onChange={handleFilterChange}
              options={STATUS_FILTERS}
            />
          }
        >
          {loadError ? (
            <Alert type="error" showIcon message={loadError} />
          ) : (
            <Table
              rowKey="notification_id"
              columns={columns}
              dataSource={notifications}
              loading={loading}
              size="middle"
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              scroll={{ x: 'max-content' }}
              locale={{
                emptyText: (
                  <Empty
                    description={
                      statusFilter === 'All'
                        ? 'No messages yet'
                        : `No ${statusFilter.toLowerCase()} messages`
                    }
                  />
                ),
              }}
            />
          )}
          {!loadError && notifications.length >= 500 && (
            <Text type="secondary" style={{ display: 'block', marginTop: 12, fontSize: 12 }}>
              Showing the 500 most recent messages.
            </Text>
          )}
        </Card>
      </motion.div>
    </div>
  );
}
