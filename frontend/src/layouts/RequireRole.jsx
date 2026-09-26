import { Link, Outlet, useOutletContext } from 'react-router-dom';
import { Button, Result } from 'antd';
import { hasRole } from '../constants/roles';

/**
 * Layout route that only renders its child routes for the given roles.
 * Pages behind it never mount for other roles, so they never make API
 * calls the backend would reject with 403.
 */
export default function RequireRole({ roles }) {
  const context = useOutletContext();

  if (!hasRole(context?.user, roles)) {
    return (
      <Result
        status="403"
        title="Not available for your role"
        subTitle="This page shows individual trainee records, which only admins can access."
        extra={
          <Link to="/dashboard">
            <Button type="primary">Back to dashboard</Button>
          </Link>
        }
      />
    );
  }

  // Pass StaffLayout's context ({ user }) through to the pages
  return <Outlet context={context} />;
}
