import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { BrandLoader } from "@/components/BrandLoader";
import { PendingWorkspace } from "@/components/PendingWorkspace";
import { ForcePasswordChange } from "@/components/ForcePasswordChange";

const isSuper = (u) => u?.platform_role === "super_admin";

export function ProtectedRoute({ children }) {
  const { user } = useAuth();
  if (user === null) return <BrandLoader />;
  if (user === false) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <ForcePasswordChange />;
  if (!isSuper(user) && user.enterprise?.status !== "active") return <PendingWorkspace />;
  return children;
}

export function SuperAdminRoute({ children }) {
  const { user } = useAuth();
  if (!isSuper(user)) return <Navigate to="/" replace />;
  return children;
}
