import { createContext, useContext, useEffect, useState } from "react";
import { api, setToken, clearToken, getToken, apiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=anon, object=auth
  useEffect(() => {
    if (!getToken()) { setUser(false); return; }
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => { clearToken(); setUser(false); });
  }, []);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch { /* noop */ }
    clearToken();
    setUser(false);
    window.location.href = "/login";
  };

  return <AuthContext.Provider value={{ user, setUser, login, register, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
export { apiError };
