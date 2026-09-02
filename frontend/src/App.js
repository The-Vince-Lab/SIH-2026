import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import Login from "@/pages/Login";
import ProviderDashboard from "@/pages/ProviderDashboard";
import AdminDashboard from "@/pages/AdminDashboard";
import TraineeProfile from "@/pages/TraineeProfile";
import MessagingSimulator from "@/pages/MessagingSimulator";
import EmployerVerify from "@/pages/EmployerVerify";

function RoleHome() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "provider" ? "/provider" : "/admin"} replace />;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster position="top-right" richColors offset="80px" />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/verify/:token" element={<EmployerVerify />} />
          <Route path="/" element={<ProtectedRoute><RoleHome /></ProtectedRoute>} />
          <Route path="/provider" element={<ProtectedRoute roles={["provider"]}><ProviderDashboard /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute roles={["district_admin", "state_admin", "super_admin"]}><AdminDashboard /></ProtectedRoute>} />
          <Route path="/trainee/:id" element={<ProtectedRoute><TraineeProfile /></ProtectedRoute>} />
          <Route path="/simulator/:traineeId" element={<ProtectedRoute><MessagingSimulator /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
