import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Trainees from "./pages/Trainees";
import TraineeDetail from "./pages/TraineeDetail";
import RegisterTrainee from "./pages/RegisterTrainee";
import Followups from "./pages/Followups";
import StaffLayout from "./layouts/StaffLayout";

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
          <Route path="/trainees" element={<Trainees />} />
          <Route path="/trainees/register" element={<RegisterTrainee />} />
          <Route path="/trainees/:id" element={<TraineeDetail />} />
          <Route path="/followups" element={<Followups />} />
        </Route>

        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;