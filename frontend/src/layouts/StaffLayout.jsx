import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate, Link } from 'react-router-dom';
import { Layout, Menu, Tag, Button, Typography, Space, Spin, Avatar } from 'antd';
import {
  DashboardOutlined,
  TeamOutlined,
  UserAddOutlined,
  PhoneOutlined,
  MessageOutlined,
  BankOutlined,
  UploadOutlined,
  BarChartOutlined,
  BulbOutlined,
  IdcardOutlined,
  LineChartOutlined,
  LogoutOutlined,
  UserOutlined,
  MenuUnfoldOutlined,
  MenuFoldOutlined,
} from '@ant-design/icons';
import { getMe, logout } from '../api/client';
import { ADMIN_ONLY, ANALYTICS_ROLES, hasRole } from '../constants/roles';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const MENU_ITEMS = [
  {
    key: '/dashboard',
    roles: ANALYTICS_ROLES,
    icon: <DashboardOutlined />,
    label: <Link to="/dashboard">Home</Link>,
  },
  {
    key: '/trainees',
    roles: ADMIN_ONLY,
    icon: <TeamOutlined />,
    label: <Link to="/trainees">Trainees</Link>,
  },
  {
    key: '/trainees/register',
    roles: ADMIN_ONLY,
    icon: <UserAddOutlined />,
    label: <Link to="/trainees/register">Register trainee</Link>,
  },
  {
    key: '/followups',
    roles: ADMIN_ONLY,
    icon: <PhoneOutlined />,
    label: <Link to="/followups">Follow-ups</Link>,
  },
  {
    key: '/messages',
    roles: ADMIN_ONLY,
    icon: <MessageOutlined />,
    label: <Link to="/messages">Messages</Link>,
  },
  {
    key: '/employers',
    roles: ADMIN_ONLY,
    icon: <BankOutlined />,
    label: <Link to="/employers">Employers</Link>,
  },
  {
    key: '/wage-history',
    roles: ADMIN_ONLY,
    icon: <LineChartOutlined />,
    label: <Link to="/wage-history">Wage history</Link>,
  },
  {
    key: '/import-placements',
    roles: ADMIN_ONLY,
    icon: <UploadOutlined />,
    label: <Link to="/import-placements">Import placements</Link>,
  },
  {
    key: '/identity',
    roles: ADMIN_ONLY,
    icon: <IdcardOutlined />,
    label: <Link to="/identity">Identity</Link>,
  },
  {
    key: '/analytics',
    roles: ANALYTICS_ROLES,
    icon: <BarChartOutlined />,
    label: <Link to="/analytics">Analytics</Link>,
  },
  {
    key: '/insights',
    roles: ANALYTICS_ROLES,
    icon: <BulbOutlined />,
    label: <Link to="/insights">Insights</Link>,
  },
];

export default function StaffLayout() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
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

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  // Only show pages the user's role can open (roles is ours, not a Menu prop)
  const menuItems = MENU_ITEMS.filter((item) => hasRole(user, item.roles)).map(
    // eslint-disable-next-line no-unused-vars
    ({ roles, ...item }) => item
  );

  // Find active key from current path
  const selectedKey =
    MENU_ITEMS.find((item) => location.pathname === item.key)?.key ||
    (location.pathname.startsWith('/trainees/register')
      ? '/trainees/register'
      : location.pathname.startsWith('/trainees')
        ? '/trainees'
        : location.pathname);

  if (loading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          backgroundColor: '#f5f7fa',
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* Collapsible Fixed Left Sidebar */}
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={(value) => setCollapsed(value)}
        trigger={null}
        width={240}
        collapsedWidth={80}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          backgroundColor: '#001529',
          zIndex: 100,
          transition: 'all 0.2s ease',
        }}
      >
        {/* Sidebar Header with Toggle Button */}
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'space-between',
            padding: collapsed ? '0' : '0 16px',
            color: '#ffffff',
            borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
            transition: 'all 0.2s ease',
          }}
        >
          {!collapsed && (
            <span
              style={{
                fontWeight: 700,
                fontSize: 16,
                letterSpacing: '0.5px',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              Staff Portal
            </span>
          )}
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{
              fontSize: '16px',
              color: '#ffffff',
              width: 40,
              height: 40,
            }}
          />
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          style={{ marginTop: 8 }}
        />
      </Sider>

      {/* Main Layout Area */}
      <Layout
        style={{
          marginLeft: collapsed ? 80 : 240,
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          transition: 'margin-left 0.2s ease',
        }}
      >
        {/* Top Bar Header */}
        <Header
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 90,
            backgroundColor: '#ffffff',
            padding: '0 28px',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            borderBottom: '1px solid #eef0f3',
            boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)',
            height: 64,
          }}
        >
          <Space size={16}>
            <Space size={8} align="center">
              <Avatar
                size="small"
                icon={<UserOutlined />}
                style={{ backgroundColor: '#1677ff' }}
              />
              <Text strong style={{ fontSize: 14 }}>
                {user?.username || 'Staff'}
              </Text>
              <Tag
                color="blue"
                style={{
                  fontSize: 11,
                  textTransform: 'uppercase',
                  fontWeight: 600,
                  margin: 0,
                }}
              >
                {user?.role || 'admin'}
              </Tag>
            </Space>

            <Button
              type="text"
              icon={<LogoutOutlined />}
              onClick={handleLogout}
              style={{ color: '#ff4d4f' }}
            >
              Logout
            </Button>
          </Space>
        </Header>

        {/* Content Body */}
        <Content
          style={{
            backgroundColor: '#f5f7fa',
            padding: '28px',
            flex: 1,
          }}
        >
          <Outlet context={{ user }} />
        </Content>
      </Layout>
    </Layout>
  );
}
