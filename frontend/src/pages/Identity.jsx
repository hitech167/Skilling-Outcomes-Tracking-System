import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Card,
  Table,
  Tag,
  Button,
  Typography,
  Form,
  Input,
  AutoComplete,
  Descriptions,
  Alert,
  Empty,
  Spin,
  Row,
  Col,
} from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  UserOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { api } from '../api/client';
import { ID_TYPE_OPTIONS, idTypeRules, idValueRules, filterIdType } from '../constants/identity';

const { Title, Text } = Typography;

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

const cardStyle = {
  borderRadius: 12,
  border: '1px solid #eef0f3',
  boxShadow: '0 4px 14px rgba(0, 0, 0, 0.03)',
};

function errorText(err, fallback) {
  const detail = err?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ');
  return fallback;
}

function ConsentTag({ given }) {
  return given ? (
    <Tag icon={<CheckCircleOutlined />} color="success">
      Consent given
    </Tag>
  ) : (
    <Tag icon={<CloseCircleOutlined />} color="error">
      Consent withdrawn
    </Tag>
  );
}

/** Profiles of every trainee in one duplicate group, side by side for review. */
function DuplicateGroupDetail({ traineeIds }) {
  const [profiles, setProfiles] = useState(null);

  useEffect(() => {
    let isMounted = true;

    async function fetchProfiles() {
      const results = await Promise.allSettled(
        traineeIds.map((id) => api.get(`/api/trainees/${encodeURIComponent(id)}`))
      );
      if (isMounted) {
        setProfiles(
          results.map((r, i) =>
            r.status === 'fulfilled' ? r.value : { trainee_id: traineeIds[i], error: true }
          )
        );
      }
    }

    fetchProfiles();

    return () => {
      isMounted = false;
    };
  }, [traineeIds]);

  if (!profiles) {
    return (
      <div style={{ textAlign: 'center', padding: '16px 0' }}>
        <Spin />
      </div>
    );
  }

  return (
    <Row gutter={[16, 16]}>
      {profiles.map((p) => (
        <Col xs={24} md={12} xl={8} key={p.trainee_id}>
          <Card size="small" style={{ borderRadius: 10 }}>
            {p.error ? (
              <Text type="danger">Could not load {p.trainee_id}</Text>
            ) : (
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Trainee">
                  <Link to={`/trainees/${p.trainee_id}`}>{p.trainee_id}</Link>
                </Descriptions.Item>
                <Descriptions.Item label="Name">{p.full_name}</Descriptions.Item>
                <Descriptions.Item label="District">{p.district}</Descriptions.Item>
                <Descriptions.Item label="Location">{p.current_location || '—'}</Descriptions.Item>
                <Descriptions.Item label="Contact via">{p.preferred_contact}</Descriptions.Item>
                <Descriptions.Item label="Consent">
                  <ConsentTag given={p.consent_given} />
                </Descriptions.Item>
              </Descriptions>
            )}
          </Card>
        </Col>
      ))}
    </Row>
  );
}

export default function Identity() {
  const [lookupForm] = Form.useForm();
  const [lookingUp, setLookingUp] = useState(false);
  const [lookupResult, setLookupResult] = useState(null);
  const [lookupError, setLookupError] = useState(null);

  const [duplicates, setDuplicates] = useState(null);
  const [dupLoading, setDupLoading] = useState(true);
  const [dupError, setDupError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    document.title = 'Identity — Skilling Outcomes Tracking System';
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function fetchDuplicates() {
      try {
        const data = await api.get('/api/identity/possible-duplicates');
        if (isMounted) {
          setDuplicates(data);
          setDupError(null);
        }
      } catch (err) {
        if (isMounted) setDupError(errorText(err, 'Failed to load possible duplicates.'));
      } finally {
        if (isMounted) setDupLoading(false);
      }
    }

    fetchDuplicates();

    return () => {
      isMounted = false;
    };
  }, [reloadKey]);

  const reloadDuplicates = () => {
    setDupLoading(true);
    setReloadKey((k) => k + 1);
  };

  const handleLookup = async (values) => {
    setLookingUp(true);
    setLookupError(null);
    setLookupResult(null);
    try {
      const params = new URLSearchParams({
        id_type: values.id_type.trim(),
        id_value: values.id_value.trim(),
      });
      const match = await api.get(`/api/identity/lookup?${params}`);
      let profile = null;
      try {
        profile = await api.get(`/api/trainees/${encodeURIComponent(match.trainee_id)}`);
      } catch {
        // Still show the matched trainee_id even if the profile can't be loaded
      }
      setLookupResult({ match, profile });
    } catch (err) {
      setLookupError(
        err?.status === 404
          ? { type: 'info', text: errorText(err, 'No trainee is linked to this ID.') }
          : { type: 'error', text: errorText(err, 'Lookup failed. Please try again.') }
      );
    } finally {
      setLookingUp(false);
    }
  };

  const duplicateColumns = [
    {
      title: 'Name',
      dataIndex: 'full_name',
      key: 'full_name',
      sorter: (a, b) => a.full_name.localeCompare(b.full_name),
    },
    {
      title: 'Date of birth',
      dataIndex: 'dob',
      key: 'dob',
      render: (dob) => new Date(`${dob}T00:00:00`).toLocaleDateString(),
    },
    {
      title: 'Records',
      key: 'count',
      align: 'right',
      width: 100,
      render: (_, row) => row.trainee_ids.length,
      sorter: (a, b) => a.trainee_ids.length - b.trainee_ids.length,
    },
    {
      title: 'Trainee IDs',
      dataIndex: 'trainee_ids',
      key: 'trainee_ids',
      render: (ids) => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {ids.map((id) => (
            <Link key={id} to={`/trainees/${id}`}>
              <Tag color="blue" style={{ margin: 0, cursor: 'pointer' }}>
                {id}
              </Tag>
            </Link>
          ))}
        </div>
      ),
    },
  ];

  const groups = duplicates?.groups || [];

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Identity
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Find trainees by IDs from other programmes and review records that may belong to the same
          person.
        </Text>
      </div>

      <motion.div variants={containerVariants} initial="hidden" animate="visible">
        {/* Lookup */}
        <motion.div variants={itemVariants} style={{ marginBottom: 24 }}>
          <Card style={cardStyle} title="Look up trainee by external ID">
            <Form form={lookupForm} layout="inline" onFinish={handleLookup} style={{ rowGap: 12 }}>
              <Form.Item name="id_type" rules={idTypeRules} style={{ minWidth: 240 }}>
                <AutoComplete
                  options={ID_TYPE_OPTIONS}
                  placeholder="ID type, e.g. Skill India Digital ID"
                  filterOption={filterIdType}
                />
              </Form.Item>
              <Form.Item name="id_value" rules={idValueRules} style={{ minWidth: 220 }}>
                <Input placeholder="ID value" allowClear />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={lookingUp}>
                  Look up
                </Button>
              </Form.Item>
            </Form>
            <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
              ID type is matched case-insensitively. ID values are compared in upper case.
            </Text>

            {lookupError && (
              <Alert
                type={lookupError.type}
                showIcon
                message={lookupError.text}
                style={{ marginTop: 16 }}
              />
            )}

            {lookupResult && (
              <Card
                size="small"
                style={{ marginTop: 16, borderRadius: 10, borderColor: '#b7eb8f', backgroundColor: '#f6ffed' }}
                title={
                  <span>
                    <UserOutlined style={{ marginRight: 8 }} />
                    Match found: {lookupResult.match.id_type} {lookupResult.match.id_value}
                  </span>
                }
                extra={
                  <Link to={`/trainees/${lookupResult.match.trainee_id}`}>
                    <Button type="link" style={{ padding: 0 }}>
                      Open profile
                    </Button>
                  </Link>
                }
              >
                <Descriptions column={{ xs: 1, md: 2 }} size="small">
                  <Descriptions.Item label="Trainee ID">
                    <Text code>{lookupResult.match.trainee_id}</Text>
                  </Descriptions.Item>
                  {lookupResult.profile ? (
                    <>
                      <Descriptions.Item label="Name">{lookupResult.profile.full_name}</Descriptions.Item>
                      <Descriptions.Item label="District">{lookupResult.profile.district}</Descriptions.Item>
                      <Descriptions.Item label="Location">
                        {lookupResult.profile.current_location || '—'}
                      </Descriptions.Item>
                      <Descriptions.Item label="Consent">
                        <ConsentTag given={lookupResult.profile.consent_given} />
                      </Descriptions.Item>
                    </>
                  ) : (
                    <Descriptions.Item label="Profile">
                      <Text type="secondary">Could not load profile details</Text>
                    </Descriptions.Item>
                  )}
                </Descriptions>
              </Card>
            )}
          </Card>
        </motion.div>

        {/* Possible duplicates */}
        <motion.div variants={itemVariants}>
          <Card
            style={cardStyle}
            title="Possible duplicates"
            extra={
              <Button icon={<ReloadOutlined />} onClick={reloadDuplicates} disabled={dupLoading}>
                Refresh
              </Button>
            }
          >
            {dupError ? (
              <Alert type="error" showIcon message={dupError} />
            ) : (
              <>
                {!dupLoading && groups.length > 0 && (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={`${groups.length} group(s) covering ${duplicates.trainees_involved} trainee records share the same name and date of birth.`}
                    description="These are flagged for review only and are never merged automatically. Expand a row to compare the records."
                  />
                )}
                <Table
                  rowKey={(row) => row.trainee_ids.join('|')}
                  columns={duplicateColumns}
                  dataSource={groups}
                  loading={dupLoading}
                  size="middle"
                  pagination={{ pageSize: 10, hideOnSinglePage: true }}
                  scroll={{ x: 'max-content' }}
                  expandable={{
                    expandedRowRender: (row) => <DuplicateGroupDetail traineeIds={row.trainee_ids} />,
                  }}
                  locale={{
                    emptyText: <Empty description="No possible duplicates found" />,
                  }}
                />
              </>
            )}
          </Card>
        </motion.div>
      </motion.div>
    </div>
  );
}
