import { createContext, useContext, useEffect, useState } from "react";
import { api, setToken, clearToken, getToken, apiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=anon, object=auth
  useEffect(() => {
    // Returning from Google OAuth: let AuthCallback exchange the session_id first.
    if (window.location.hash?.includes("session_id=")) return;
    // Works for both JWT (Bearer) and Google (httpOnly session cookie).
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => { clearToken(); setUser(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    setToken(data.access_token);
    const me = await api.get("/auth/me");
    setUser(me.data);
    return me.data;
  };

  // Returns { requires_verification, email } — does NOT log the user in.
  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    return data;
  };

  const registerEnterprise = async (payload) => {
    const { data } = await api.post("/auth/register-enterprise", payload);
    return data;
  };

  const verifyOtp = async (email, code) => {
    const { data } = await api.post("/auth/verify-otp", { email, code });
    setToken(data.access_token);
    const me = await api.get("/auth/me");
    setUser(me.data);
    return me.data;
  };

  const resendOtp = async (email) => {
    await api.post("/auth/resend-otp", { email });
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) { console.debug("logout request failed", e); }
    clearToken();
    setUser(false);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, setUser, login, register, registerEnterprise, verifyOtp, resendOtp, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
export { apiError };
