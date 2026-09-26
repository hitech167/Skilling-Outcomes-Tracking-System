import { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Upload,
  AutoComplete,
  Switch,
  Button,
  Typography,
  Row,
  Col,
  Table,
  Tag,
  Alert,
  Collapse,
  message,
} from 'antd';
import {
  InboxOutlined,
  UploadOutlined,
  ExperimentOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const { Title, Text, Paragraph } = Typography;
const { Dragger } = Upload;

const SOURCE_SUGGESTIONS = ['EPFO', 'ESIC', 'NCS portal', 'Job portal', 'Employer HR sheet'].map(
  (value) => ({ value })
);

const SAMPLE_CSV = `trainee_id,employer_name,job_role,start_date,monthly_salary,reference
TRN000001,Volt Works Pvt Ltd,Electrician,2025-06-01,17000,UAN123`;

// Result keys returned by POST /api/employment-signals/import
const RESULT_STATS = [
  { key: 'created', label: 'Employed recorded', color: '#389e0d', hint: 'New Employed outcome + verified employment' },
  { key: 'verified_existing', label: 'Existing verified', color: '#1677ff', hint: 'Pending verification resolved' },
  { key: 'already_recorded', label: 'Already recorded', color: '#1f2937', hint: 'Employer already on record, nothing changed' },
  { key: 'trainee_not_found', label: 'Trainee not found', color: '#cf1322', hint: 'No trainee matched this row' },
  { key: 'no_training', label: 'No training record', color: '#d46b08', hint: 'Trainee has no training to attach an outcome to' },
  { key: 'no_consent', label: 'No consent', color: '#8c8c8c', hint: 'Skipped: trainee has not given consent' },
  { key: 'invalid', label: 'Invalid rows', color: '#cf1322', hint: 'Bad date, salary or missing employer' },
];

const PROBLEM_LABELS = {
  invalid: { label: 'Invalid', color: 'red' },
  trainee_not_found: { label: 'Trainee not found', color: 'volcano' },
  no_training: { label: 'No training record', color: 'orange' },
};

const MAX_REPORTED_PROBLEMS = 50;

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

function ResultSummary({ result }) {
  const matched =
    result.created +
    result.verified_existing +
    result.already_recorded +
    result.no_consent +
    result.no_training;
  const failedCount = result.invalid + result.trainee_not_found + result.no_training;

  return (
    <>
      <Alert
        type={result.dry_run ? 'info' : 'success'}
        showIcon
        style={{ marginBottom: 20 }}
        message={
          result.dry_run
            ? `Dry run: ${result.rows} row(s) checked from ${result.source}. Nothing was saved.`
            : `Imported ${result.rows} row(s) from ${result.source}.`
        }
        description={`${matched} of ${result.rows} row(s) matched a trainee. ${
          result.dry_run ? 'Would record' : 'Recorded'
        } ${result.created} new Employed outcome(s).`}
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} md={6}>
          <Card size="small" style={{ ...cardStyle, height: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>Rows in file</Text>
            <div style={{ fontSize: 24, fontWeight: 600, color: '#1f2937' }}>{result.rows}</div>
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small" style={{ ...cardStyle, height: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>Matched trainees</Text>
            <div style={{ fontSize: 24, fontWeight: 600, color: '#1f2937' }}>{matched}</div>
          </Card>
        </Col>
        {RESULT_STATS.map((stat) => (
          <Col xs={12} md={6} key={stat.key}>
            <Card size="small" style={{ ...cardStyle, height: '100%' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {stat.label}
              </Text>
              <div
                style={{
                  fontSize: 24,
                  fontWeight: 600,
                  color: result[stat.key] > 0 ? stat.color : '#bfbfbf',
                }}
              >
                {result[stat.key]}
              </div>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {stat.hint}
              </Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Title level={5} style={{ marginTop: 0 }}>
        Rows that need attention
      </Title>
      {failedCount > result.problems.length && (
        <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
          Showing the first {Math.min(result.problems.length, MAX_REPORTED_PROBLEMS)} of{' '}
          {failedCount} problem rows.
        </Text>
      )}
      <Table
        rowKey="row"
        size="small"
        dataSource={result.problems}
        pagination={{ pageSize: 10, hideOnSinglePage: true }}
        locale={{ emptyText: 'No problem rows' }}
        columns={[
          { title: 'CSV row', dataIndex: 'row', key: 'row', width: 100 },
          {
            title: 'Result',
            dataIndex: 'result',
            key: 'result',
            width: 180,
            render: (value) => {
              const p = PROBLEM_LABELS[value];
              return <Tag color={p?.color || 'default'}>{p?.label || value}</Tag>;
            },
          },
          {
            title: 'Error',
            dataIndex: 'detail',
            key: 'detail',
            render: (detail, row) =>
              detail ||
              (row.result === 'trainee_not_found'
                ? 'No trainee matches the trainee_id / phone / external_id'
                : row.result === 'no_training'
                ? 'Trainee has no training record'
                : '—'),
          },
        ]}
      />
    </>
  );
}

export default function ImportPlacements() {
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    document.title = 'Import Placements — Skilling Outcomes Tracking System';
  }, []);

  const runImport = async ({ source, dryRun }) => {
    const file = fileList[0]?.originFileObj || fileList[0];
    if (!file) {
      message.warning('Please choose a CSV file.');
      return;
    }

    const body = new FormData();
    body.append('file', file);
    body.append('source', source.trim());
    body.append('dry_run', dryRun ? 'true' : 'false');

    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post('/api/employment-signals/import', body);
      setResult(res);
      if (res.dry_run) {
        message.info('Dry run complete. Nothing was saved.');
      } else {
        message.success(`Import complete: ${res.created} Employed outcome(s) recorded.`);
      }
    } catch (err) {
      const detail = err?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
          ? detail.map((d) => d.msg).join('; ')
          : 'Import failed. Please try again.'
      );
      setResult(null);
    } finally {
      setSubmitting(false);
    }
  };

  const handleFinish = (values) => runImport({ source: values.source, dryRun: values.dry_run });

  const handleImportForReal = () => {
    form.setFieldValue('dry_run', false);
    runImport({ source: form.getFieldValue('source'), dryRun: false });
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Import Placements
        </Title>
        <Text type="secondary" style={{ fontSize: 14 }}>
          Upload placement data from an outside source to record verified employment outcomes.
        </Text>
      </div>

      <motion.div variants={containerVariants} initial="hidden" animate="visible">
        <motion.div variants={itemVariants} style={{ marginBottom: 24 }}>
          <Card style={cardStyle} title="Upload CSV">
            <Form
              form={form}
              layout="vertical"
              initialValues={{ dry_run: true }}
              onFinish={handleFinish}
              requiredMark="optional"
            >
              <Form.Item label="CSV file" required>
                <Dragger
                  accept=".csv,text/csv"
                  maxCount={1}
                  fileList={fileList}
                  beforeUpload={() => false}
                  onChange={({ fileList: next }) => {
                    setFileList(next.slice(-1));
                    setResult(null);
                    setError(null);
                  }}
                  onRemove={() => setFileList([])}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">Click or drag a CSV file here</p>
                  <p className="ant-upload-hint">UTF-8 CSV, up to 2 MB and 5,000 rows.</p>
                </Dragger>
              </Form.Item>

              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Source"
                    name="source"
                    tooltip="Where the data comes from. Recorded as the verifier on each placement."
                    rules={[
                      { required: true, whitespace: true, message: 'Please enter the data source' },
                      { min: 2, max: 60, message: 'Source must be 2–60 characters' },
                    ]}
                  >
                    <AutoComplete
                      options={SOURCE_SUGGESTIONS}
                      placeholder="e.g. EPFO, job portal"
                      filterOption={(input, option) =>
                        option.value.toLowerCase().includes(input.toLowerCase())
                      }
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Dry run"
                    name="dry_run"
                    valuePropName="checked"
                    extra="Check the file and see what would happen, without saving anything."
                  >
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item shouldUpdate style={{ marginBottom: 0 }}>
                {() => {
                  const dryRun = form.getFieldValue('dry_run');
                  return (
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={submitting}
                      disabled={fileList.length === 0}
                      icon={dryRun ? <ExperimentOutlined /> : <UploadOutlined />}
                    >
                      {dryRun ? 'Check file (dry run)' : 'Import placements'}
                    </Button>
                  );
                }}
              </Form.Item>
            </Form>

            <Collapse
              ghost
              style={{ marginTop: 16 }}
              items={[
                {
                  key: 'format',
                  label: 'CSV format',
                  children: (
                    <>
                      <Paragraph style={{ fontSize: 13 }}>
                        Required columns: <Text code>employer_name</Text>,{' '}
                        <Text code>start_date</Text> (YYYY-MM-DD), and at least one of{' '}
                        <Text code>trainee_id</Text>, <Text code>phone</Text>, or{' '}
                        <Text code>external_id</Text> (as <Text code>TYPE:VALUE</Text>). Optional:{' '}
                        <Text code>job_role</Text>, <Text code>monthly_salary</Text>,{' '}
                        <Text code>reference</Text>.
                      </Paragraph>
                      <Paragraph copyable={{ text: SAMPLE_CSV }} style={{ marginBottom: 0 }}>
                        <pre style={{ margin: 0, fontSize: 12, overflowX: 'auto' }}>{SAMPLE_CSV}</pre>
                      </Paragraph>
                    </>
                  ),
                },
              ]}
            />
          </Card>
        </motion.div>

        {error && (
          <motion.div variants={itemVariants} initial="hidden" animate="visible" style={{ marginBottom: 24 }}>
            <Alert type="error" showIcon message="Import failed" description={error} />
          </motion.div>
        )}

        {result && (
          <motion.div variants={itemVariants} initial="hidden" animate="visible">
            <Card
              style={cardStyle}
              title={result.dry_run ? 'Dry run results' : 'Import results'}
              extra={
                result.dry_run &&
                result.created + result.verified_existing > 0 && (
                  <Button
                    type="primary"
                    icon={<CheckCircleOutlined />}
                    loading={submitting}
                    onClick={handleImportForReal}
                  >
                    Import for real
                  </Button>
                )
              }
            >
              <ResultSummary result={result} />
            </Card>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}
