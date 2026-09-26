import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Trainees from "./pages/Trainees";
import TraineeDetail from "./pages/TraineeDetail";
import RegisterTrainee from "./pages/RegisterTrainee";
import Followups from "./pages/Followups";
import Analytics from "./pages/Analytics";
import Employers from "./pages/Employers";
import Messages from "./pages/Messages";
import ImportPlacements from "./pages/ImportPlacements";
import Insights from "./pages/Insights";
import Identity from "./pages/Identity";
import WageHistory from "./pages/WageHistory";
import StaffLayout from "./layouts/StaffLayout";
import RequireRole from "./layouts/RequireRole";
import { ADMIN_ONLY, ANALYTICS_ROLES } from "./constants/roles";

function ProtectedRoute({ children }) {
  const token = sessionStorage.getItem("token");
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function RootRedirect() {
  const token = sessionStorage.getItem("token");
  return <Navigate to={token ? "/dashboard" : "/login"} replace />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<Login />} />

        {/* Protected Admin/Staff Routes with shared StaffLayout */}
        <Route
          element={
            <ProtectedRoute>
              <StaffLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />

          {/* Aggregated, no personal data: admin + analyst */}
          <Route element={<RequireRole roles={ANALYTICS_ROLES} />}>
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/insights" element={<Insights />} />
          </Route>

          {/* Individual trainee records: admin only (matches backend ADMIN_ONLY routers) */}
          <Route element={<RequireRole roles={ADMIN_ONLY} />}>
            <Route path="/trainees" element={<Trainees />} />
            <Route path="/trainees/register" element={<RegisterTrainee />} />
            <Route path="/trainees/:id" element={<TraineeDetail />} />
            <Route path="/followups" element={<Followups />} />
            <Route path="/identity" element={<Identity />} />
            <Route path="/wage-history" element={<WageHistory />} />
            <Route path="/employers" element={<Employers />} />
            <Route path="/messages" element={<Messages />} />
            <Route path="/import-placements" element={<ImportPlacements />} />
          </Route>
        </Route>

        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;