"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ApiClient } from "@/lib/apiClient";

export interface User {
  id: string;
  username: string;
  email: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  signup: (username: string, email: string, password: str) => Promise<{ success: boolean; error?: string; role?: string }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const router = useRouter();
  const pathname = usePathname();

  // Validate existing session on mount & refresh
  const refreshUser = async () => {
    try {
      const savedToken = ApiClient.getToken();
      if (!savedToken) {
        setUser(null);
        setToken(null);
        setLoading(false);
        return;
      }
      setToken(savedToken);

      const res = await fetch(ApiClient.getUrl("/api/auth/me"), {
        headers: ApiClient.getHeaders(),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.user) {
          setUser(data.user);
          localStorage.setItem("queryiq_user", JSON.stringify(data.user));
        }
      } else {
        // Token expired or invalid
        localStorage.removeItem("queryiq_token");
        localStorage.removeItem("queryiq_user");
        localStorage.removeItem("token");
        setUser(null);
        setToken(null);
      }
    } catch (err) {
      console.error("[AUTH] Error checking user session:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshUser();
  }, []);

  // Login handler
  const login = async (username: str, password: str) => {
    try {
      const res = await fetch(ApiClient.getUrl("/api/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();
      if (!res.ok || data.status === "error") {
        return { success: false, error: data.detail || data.message || "Invalid username or password" };
      }

      const authToken = data.access_token;
      const userData = data.user;

      localStorage.setItem("queryiq_token", authToken);
      localStorage.setItem("queryiq_user", JSON.stringify(userData));
      if (data.refresh_token) {
        localStorage.setItem("queryiq_refresh_token", data.refresh_token);
      }

      setToken(authToken);
      setUser(userData);

      return { success: true };
    } catch (err: any) {
      return { success: false, error: err.message || "Failed to connect to authentication server." };
    }
  };

  // Signup handler
  const signup = async (username: str, email: str, password: str) => {
    try {
      const res = await fetch(ApiClient.getUrl("/api/auth/signup"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password }),
      });

      const data = await res.json();
      if (!res.ok || data.status === "error") {
        return { success: false, error: data.detail || data.message || "Registration failed." };
      }

      // Auto login after signup
      const loginRes = await login(username, password);
      if (loginRes.success) {
        return { success: true, role: data.role };
      }

      return { success: true, role: data.role };
    } catch (err: any) {
      return { success: false, error: err.message || "Failed to connect to authentication server." };
    }
  };

  // Logout handler
  const logout = async () => {
    try {
      if (token) {
        await fetch(ApiClient.getUrl("/api/auth/logout"), {
          method: "POST",
          headers: ApiClient.getHeaders(),
        });
      }
    } catch (e) {
      console.warn("[AUTH] Logout error:", e);
    } finally {
      localStorage.removeItem("queryiq_token");
      localStorage.removeItem("queryiq_user");
      localStorage.removeItem("queryiq_refresh_token");
      localStorage.removeItem("token");
      setUser(null);
      setToken(null);
      router.push("/login");
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
