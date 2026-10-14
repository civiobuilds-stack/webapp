import "@/App.css";
import { useEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppShell } from "@/components/AppShell";
import { Toaster } from "@/components/ui/sonner";
import { api } from "@/lib/api";
import { Loader2 } from "lucide-react";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import Projects from "@/pages/Projects";
import ProjectDetail from "@/pages/ProjectDetail";
import People from "@/pages/People";
import Notifications from "@/pages/Notifications";
import SuperAdmin from "@/pages/SuperAdmin";
import { SuperAdminRoute } from "@/components/ProtectedRoute";

function Shell({ children }) {
  return <ProtectedRoute><AppShell>{children}</AppShell></ProtectedRoute>;
}

// Handles the Google OAuth return: exchanges session_id for a session, then redirects.
function AuthCallback() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const processed = useRef(false);
  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const sid = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("session_id");
    if (!sid) { navigate("/login"); return; }
    api.post("/auth/google/session", { session_id: sid })
      .then(() => api.get("/auth/me"))
      .then((r) => { window.history.replaceState(null, "", "/"); setUser(r.data); navigate(r.data.platform_role === "super_admin" ? "/superadmin" : "/"); })
      .catch(() => { window.history.replaceState(null, "", "/"); navigate("/login"); });
  }, [navigate, setUser]);
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm">Signing you in…</p>
      </div>
    </div>
  );
}

function AppRouter() {
  const location = useLocation();
  // Synchronous check (not in useEffect) to win the race before ProtectedRoute runs.
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/" element={<Shell><Dashboard /></Shell>} />
      <Route path="/projects" element={<Shell><Projects /></Shell>} />
      <Route path="/projects/:id" element={<Shell><ProjectDetail /></Shell>} />
      <Route path="/people" element={<Shell><People /></Shell>} />
      <Route path="/notifications" element={<Shell><Notifications /></Shell>} />
      <Route path="/superadmin" element={<ProtectedRoute><SuperAdminRoute><AppShell><SuperAdmin /></AppShell></SuperAdminRoute></ProtectedRoute>} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
