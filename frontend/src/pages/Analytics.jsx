import { useEffect, useState } from 'react';
import {
  Card,
  Spin,
  Typography,
  Row,
  Col,
  Table,
  Tabs,
  Progress,
  Alert,
  Empty,
  Tag,
  Statistic,
} from 'antd';
import {
  RiseOutlined,
  SolutionOutlined,
  SafetyCertificateOutlined,
  UserDeleteOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const { Title, Text } = Typography;

const ENDPOINTS = {
  placement: '/api/analytics/placement-rate',
  employment: '/api/analytics/employment-rate',
  retention: '/api/analytics/retention-rate',
  attrition: '/api/analytics/attrition',
  wages: '/api/analytics/wage-progression',
  districts: '/api/analytics/district-outcomes',
  courses: '/api/analytics/course-performance',
  providers: '/api/analytics/provider-performance',
};

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

function formatSalary(value) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function RateCard({ title, icon, color, rate, footer, loading, error }) {
  return (
    <Card style={{ ...cardStyle, height: '100%' }} styles={{ body: { padding: 24 } }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: 12,
        }}
      >
        <Text type="secondary" style={{ fontSize: 13, fontWeight: 500 }}>
          {title}
        </Text>
        <span style={{ fontSize: 22, color }}>{icon}</span>
      </div>
      {loading ? (
        <Spin />
      ) : error ? (
        <Text type="danger" style={{ fontSize: 13 }}>
          Unavailable
        </Text>
      ) : (
        <>
          <div style={{ fontSize: 30, fontWeight: 600, color: '#1f2937', lineHeight: 1.2 }}>
            {rate.toFixed(1)}%
          </div>
          <Progress
            percent={rate}
            showInfo={false}
            strokeColor={color}
            size="small"
            style={{ margin: '8px 0 4px' }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {footer}
          </Text>
        </>
      )}
    </Card>
  );
}

function groupColumns(nameKey, nameTitle) {
  return [
    {
      title: nameTitle,
      dataIndex: nameKey,
      key: nameKey,
      sorter: (a, b) => String(a[nameKey]).localeCompare(String(b[nameKey])),
    },
    {
      title: 'Trainees',
      dataIndex: 'total_trainees',
      key: 'total_trainees',
      align: 'right',
      sorter: (a, b) => a.total_trainees - b.total_trainees,
    },
    {
      title: 'Completed',
      dataIndex: 'completed',
      key: 'completed',
      align: 'right',
      sorter: (a, b) => a.completed - b.completed,
    },
    {
      title: 'Placed',
      dataIndex: 'placed',
      key: 'placed',
      align: 'right',
      sorter: (a, b) => a.placed - b.placed,
    },
    {
      title: 'Employed',
      dataIndex: 'employed',
      key: 'employed',
      align: 'right',
    },
    {
      title: 'Self-employed',
      dataIndex: 'self_employed',
      key: 'self_employed',
      align: 'right',
    },
    {
      title: 'Apprenticeship',
      dataIndex: 'apprenticeship',
      key: 'apprenticeship',
      align: 'right',
    },
    {
      title: 'Unemployed',
      dataIndex: 'unemployed',
      key: 'unemployed',
      align: 'right',
    },
    {
      title: 'Placement rate',
      dataIndex: 'placement_rate',
      key: 'placement_rate',
      width: 200,
      defaultSortOrder: 'descend',
      sorter: (a, b) => a.placement_rate - b.placement_rate,
      render: (value) => (
        <Progress percent={value} size="small" format={(p) => `${p.toFixed(1)}%`} />
      ),
    },
  ];
}

function BreakdownTable({ data, error, nameKey, nameTitle }) {
  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }
  return (
    <Table
      rowKey={nameKey}
      columns={groupColumns(nameKey, nameTitle)}
      dataSource={data || []}
      size="middle"
      pagination={{ pageSize: 10, hideOnSinglePage: true }}
      scroll={{ x: 'max-content' }}
      locale={{ emptyText: <Empty description="No data yet" /> }}
    />
  );
}

export default function Analytics() {
  const [data, setData] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.title = 'Analytics — Skilling Outcomes Tracking System';
    let isMounted = true;

    async function fetchAll() {
      const keys = Object.keys(ENDPOINTS);
      const results = await Promise.allSettled(
        keys.map((key) => api.get(ENDPOINTS[key]))
      );
      if (!isMounted) return;

      const nextData = {};
      const nextErrors = {};
      results.forEach((result, i) => {
        const key = keys[i];
        if (result.status === 'fulfilled') {
          nextData[key] = result.value;
        } else {
          const detail = result.reason?.detail;
          nextErrors[key] =
            typeof detail === 'string' ? detail : 'Could not load this section.';
        }
      });
      setData(nextData);
      setErrors(nextErrors);
      setLoading(false);
    }

    fetchAll();

    return () => {
      isMounted = false;
    };
  }, []);

  const { placement, employment, retention, attrition, wages } = data;
  const salaryChange = wages?.average_salary_change;
  const salaryGrowth = wages?.average_salary_growth_percentage;
  const growthUp = salaryChange !== null && salaryChange !== undefined && salaryChange >= 0;

  const rateCards = [
    {
      key: 'placement',
      title: 'Placement rate',
      icon: <RiseOutlined />,
      color: '#1677ff',
      rate: placement?.placement_rate,
      footer: placement && `${placement.placed_trainees} of ${placement.eligible_trainees} completed trainees placed`,
    },
    {
      key: 'employment',
      title: 'Employment rate',
      icon: <SolutionOutlined />,
      color: '#52c41a',
      rate: employment?.employment_rate,
      footer: employment && `${employment.employed_trainees} of ${employment.eligible_trainees} completed trainees employed`,
    },
    {
      key: 'retention',
      title: 'Retention rate',
      icon: <SafetyCertificateOutlined />,
      color: '#722ed1',
      rate: retention?.retention_rate,
      footer: retention && `${retention.retained_trainees} of ${retention.employed_trainees} still in their job`,
    },
    {
      key: 'attrition',
      title: 'Attrition rate',
      icon: <UserDeleteOutlined />,
      color: '#fa541c',
      rate: attrition?.attrition_rate,
      footer: attrition && `${attrition.attrition_records} of ${attrition.total_employment_records} employment records`,
    },
  ];

  const breakdownTabs = [
    {
      key: 'district',
      label: 'By district',
      children: (
        <BreakdownTable
          data={data.districts}
          error={errors.districts}
          nameKey="district"
          nameTitle="District"
        />
      ),
    },
    {
      key: 'course',
      label: 'By programme',
      children: (
        <BreakdownTable
          data={data.courses}
          error={errors.courses}
          nameKey="course_name"
          nameTitle="Programme"
        />
      ),
    },
    {
      key: 'provider',
      label: 'By provider',
      children: (
        <BreakdownTable
          data={data.providers}
          error={errors.providers}
          nameKey="provider_name"
          nameTitle="Provider"
        />
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Analytics
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Aggregate placement, employment, retention and wage outcomes across all trainees.
        </Text>
      </div>

      <motion.div variants={containerVariants} initial="hidden" animate="visible">
        {/* Summary rate cards */}
        <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
          {rateCards.map((card) => (
            <Col xs={24} sm={12} lg={6} key={card.key}>
              <motion.div variants={itemVariants} style={{ height: '100%' }}>
                <RateCard
                  {...card}
                  loading={loading}
                  error={errors[card.key]}
                />
              </motion.div>
            </Col>
          ))}
        </Row>

        {/* Wage progression */}
        <motion.div variants={itemVariants} style={{ marginBottom: 24 }}>
          <Card
            style={cardStyle}
            title="Wage progression"
            extra={
              wages?.salary_basis && (
                <Tag color="default" style={{ margin: 0 }}>
                  {wages.salary_basis}
                </Tag>
              )
            }
          >
            {loading ? (
              <Spin />
            ) : errors.wages ? (
              <Alert type="error" showIcon message={errors.wages} />
            ) : wages?.employment_records_with_wage_data ? (
              <>
                <Row gutter={[24, 24]}>
                  <Col xs={12} md={6}>
                    <Statistic
                      title="Avg. initial salary"
                      value={formatSalary(wages.average_initial_salary)}
                    />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic
                      title="Avg. latest salary"
                      value={formatSalary(wages.average_latest_salary)}
                    />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic
                      title="Avg. salary change"
                      value={formatSalary(salaryChange)}
                      valueStyle={
                        salaryChange !== null && salaryChange !== undefined
                          ? { color: growthUp ? '#3f8600' : '#cf1322' }
                          : undefined
                      }
                      prefix={
                        salaryChange !== null && salaryChange !== undefined
                          ? growthUp
                            ? <ArrowUpOutlined />
                            : <ArrowDownOutlined />
                          : null
                      }
                    />
                  </Col>
                  <Col xs={12} md={6}>
                    <Statistic
                      title="Avg. salary growth"
                      value={salaryGrowth ?? '—'}
                      precision={salaryGrowth !== null && salaryGrowth !== undefined ? 1 : undefined}
                      suffix={salaryGrowth !== null && salaryGrowth !== undefined ? '%' : undefined}
                    />
                  </Col>
                </Row>
                <Text type="secondary" style={{ display: 'block', marginTop: 16, fontSize: 12 }}>
                  Based on {wages.employment_records_with_wage_data} of{' '}
                  {wages.employment_records} employment records with wage data (
                  {wages.employment_records_with_wage_progression} with more than one
                  wage entry).
                </Text>
              </>
            ) : (
              <Empty description="No wage data recorded yet" />
            )}
          </Card>
        </motion.div>

        {/* Attrition reasons */}
        {!loading && attrition?.reasons?.length > 0 && (
          <motion.div variants={itemVariants} style={{ marginBottom: 24 }}>
            <Card style={cardStyle} title="Attrition reasons">
              {attrition.note && (
                <Alert
                  type="info"
                  showIcon
                  message={attrition.note}
                  style={{ marginBottom: 16 }}
                />
              )}
              <Table
                rowKey="reason"
                size="small"
                pagination={false}
                dataSource={attrition.reasons}
                columns={[
                  { title: 'Reason', dataIndex: 'reason', key: 'reason' },
                  {
                    title: 'Records',
                    dataIndex: 'count',
                    key: 'count',
                    align: 'right',
                    width: 120,
                  },
                ]}
              />
            </Card>
          </motion.div>
        )}

        {/* Outcome breakdowns */}
        <motion.div variants={itemVariants}>
          <Card style={cardStyle} title="Outcome breakdown">
            {loading ? <Spin /> : <Tabs items={breakdownTabs} />}
          </Card>
        </motion.div>
      </motion.div>
    </div>
  );
}
