import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Spin, Typography, Row, Col, Tag, Space } from 'antd';
import {
  TeamOutlined,
  PhoneOutlined,
  BankOutlined,
  BarChartOutlined,
  UploadOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { getMe, logout } from '../api/client';

const { Title, Text, Paragraph } = Typography;

const CARDS_CONFIG = [
  {
    key: 'trainees',
    title: 'Trainees',
    description: 'Track candidate enrollment, training batches, and profiles.',
    icon: <TeamOutlined style={{ fontSize: 30, color: '#1677ff' }} />,
    roles: ['admin'],
    path: '/trainees',
    available: true,
  },
  {
    key: 'follow-ups',
    title: 'Follow-ups',
    description: 'Monitor post-placement check-ins and outcome milestones.',
    icon: <PhoneOutlined style={{ fontSize: 30, color: '#52c41a' }} />,
    roles: ['admin'],
    path: '/followups',
    available: true,
  },
  {
    key: 'employers',
    title: 'Employers',
    description: 'Manage employer partners, vacancies, and hiring feedback.',
    icon: <BankOutlined style={{ fontSize: 30, color: '#fa8c16' }} />,
    roles: ['admin'],
    path: '/employers',
    available: true,
  },
  {
    key: 'analytics',
    title: 'Analytics',
    description: 'View aggregate placement rates, retention, and reports.',
    icon: <BarChartOutlined style={{ fontSize: 30, color: '#722ed1' }} />,
    roles: ['admin', 'analyst'],
    path: '/analytics',
    available: true,
  },
  {
    key: 'insights',
    title: 'Insights',
    description: 'Rule-based findings on skill gaps, attrition, and data quality.',
    icon: <BulbOutlined style={{ fontSize: 30, color: '#faad14' }} />,
    roles: ['admin', 'analyst'],
    path: '/insights',
    available: true,
  },
  {
    key: 'import-placements',
    title: 'Import Placements',
    description: 'Upload placement data from EPFO, job portals, or employer sheets as CSV.',
    icon: <UploadOutlined style={{ fontSize: 30, color: '#13c2c2' }} />,
    roles: ['admin'],
    path: '/import-placements',
    available: true,
  },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: 'easeOut' },
  },
};

export default function Dashboard() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Dashboard — Skilling Outcomes Tracking System";
    let isMounted = true;

    async function fetchUser() {
      try {
        const userData = await getMe();
        if (isMounted) {
          setUser(userData);
        }
      } catch (err) {
        if (err?.status === 401 || !sessionStorage.getItem('token')) {
          logout();
          navigate('/login', { replace: true });
        } else {
          navigate('/login', { replace: true });
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    fetchUser();

    return () => {
      isMounted = false;
    };
  }, [navigate]);

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '60px 0',
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  const role = user?.role?.toLowerCase() || '';
  const visibleCards = CARDS_CONFIG.filter((card) =>
    card.roles.includes(role)
  );

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Dashboard Overview
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Access modules and manage tracking data according to your permissions.
        </Text>
      </div>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <Row gutter={[24, 24]}>
          {visibleCards.map((card) => {
            const isClickable = card.available && card.path;

            return (
              <Col xs={24} sm={24} md={12} lg={12} xl={12} key={card.key}>
                <motion.div variants={itemVariants} style={{ height: '100%' }}>
                  <Card
                    hoverable={isClickable}
                    onClick={() => {
                      if (isClickable) {
                        navigate(card.path);
                      }
                    }}
                    style={{
                      height: 200,
                      borderRadius: 12,
                      border: '1px solid #eef0f3',
                      boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
                      cursor: isClickable ? 'pointer' : 'default',
                      opacity: card.available ? 1 : 0.68,
                      backgroundColor: card.available ? '#ffffff' : '#fafafa',
                      transition: 'all 0.2s ease',
                    }}
                    styles={{
                      body: {
                        padding: '24px',
                        display: 'flex',
                        flexDirection: 'column',
                        height: '100%',
                        boxSizing: 'border-box',
                      },
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        marginBottom: 16,
                      }}
                    >
                      <div
                        style={{
                          filter: card.available ? 'none' : 'grayscale(1)',
                        }}
                      >
                        {card.icon}
                      </div>
                      {!card.available && (
                        <Tag
                          color="default"
                          style={{
                            fontSize: 11,
                            margin: 0,
                            borderRadius: 4,
                            color: '#8c8c8c',
                            backgroundColor: '#f0f0f0',
                            border: 'none',
                          }}
                        >
                          Coming soon
                        </Tag>
                      )}
                    </div>

                    <Title
                      level={5}
                      style={{
                        margin: '0 0 8px 0',
                        fontWeight: 600,
                        color: card.available ? '#1f2937' : '#6b7280',
                      }}
                    >
                      {card.title}
                    </Title>

                    <Paragraph
                      type="secondary"
                      style={{
                        margin: 0,
                        fontSize: 13,
                        lineHeight: 1.5,
                        flex: 1,
                        overflow: 'hidden',
                        display: '-webkit-box',
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: 'vertical',
                      }}
                    >
                      {card.description}
                    </Paragraph>
                  </Card>
                </motion.div>
              </Col>
            );
          })}
        </Row>
      </motion.div>
    </div>
  );
}
