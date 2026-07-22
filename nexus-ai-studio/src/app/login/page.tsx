"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import Link from "next/link";

export default function LoginPage() {
  const [isSignup, setIsSignup] = useState(false);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const { login, signup } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    if (!username.trim() || !password.trim() || (isSignup && !email.trim())) {
      setError("Please fill out all required fields.");
      return;
    }

    setLoading(true);

    try {
      if (isSignup) {
        const res = await signup(username.trim(), email.trim(), password.trim());
        if (!res.success) {
          setError(res.error || "Signup failed");
          setLoading(false);
          return;
        }
        setSuccessMsg(`Welcome ${username}! Account created as ${res.role || "User"}. Redirecting...`);
        setTimeout(() => {
          router.push("/");
        }, 1200);
      } else {
        const res = await login(username.trim(), password.trim());
        if (!res.success) {
          setError(res.error || "Invalid username or password");
          setLoading(false);
          return;
        }
        setSuccessMsg("Logged in successfully! Redirecting...");
        setTimeout(() => {
          router.push("/");
        }, 800);
      }
    } catch (err: any) {
      setError(err.message || "An error occurred during authentication.");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex flex-col justify-center items-center px-4 relative overflow-hidden font-headline">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-vibrant-blue/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute bottom-10 right-10 w-[400px] h-[400px] bg-tertiary/10 rounded-full blur-3xl pointer-events-none"></div>

      {/* Main Glassmorphic Auth Card */}
      <div className="w-full max-w-md bg-surface-container/80 backdrop-blur-xl border border-outline-variant/40 rounded-2xl p-8 shadow-2xl relative z-10">
        {/* Header Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-vibrant-blue/10 border border-vibrant-blue/30 text-vibrant-blue mb-3 shadow-inner">
            <span className="material-symbols-outlined text-3xl font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>
              psychology
            </span>
          </div>
          <h1 className="text-2xl font-black tracking-tight text-deep-navy">QueryIQ</h1>
          <p className="text-xs text-on-surface-variant mt-1 font-semibold">
            Enterprise AI Data Analyst & Intelligence Engine
          </p>
        </div>

        {/* Tab Toggle (Login vs Sign Up) */}
        <div className="flex bg-surface-container-high p-1 rounded-xl mb-6 border border-outline-variant/30">
          <button
            type="button"
            onClick={() => { setIsSignup(false); setError(null); setSuccessMsg(null); }}
            className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
              !isSignup
                ? "bg-surface text-deep-navy shadow-xs border border-outline-variant/30"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            Log In
          </button>
          <button
            type="button"
            onClick={() => { setIsSignup(true); setError(null); setSuccessMsg(null); }}
            className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${
              isSignup
                ? "bg-surface text-deep-navy shadow-xs border border-outline-variant/30"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            Sign Up
          </button>
        </div>

        {/* Feedback Alerts */}
        {error && (
          <div className="mb-4 p-3 bg-error/10 border border-error/30 rounded-xl text-xs text-error font-semibold flex items-center gap-2">
            <span className="material-symbols-outlined text-base shrink-0">error</span>
            <span>{error}</span>
          </div>
        )}

        {successMsg && (
          <div className="mb-4 p-3 bg-success/10 border border-success/30 rounded-xl text-xs text-success font-semibold flex items-center gap-2">
            <span className="material-symbols-outlined text-base shrink-0">check_circle</span>
            <span>{successMsg}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-deep-navy mb-1">
              Username
            </label>
            <div className="relative">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">
                person
              </span>
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-xl pl-10 pr-4 py-2.5 text-xs text-on-surface placeholder:text-outline focus:outline-none focus:border-vibrant-blue font-semibold"
              />
            </div>
          </div>

          {isSignup && (
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-deep-navy mb-1">
                Email Address
              </label>
              <div className="relative">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">
                  mail
                </span>
                <input
                  type="email"
                  required={isSignup}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com"
                  className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-xl pl-10 pr-4 py-2.5 text-xs text-on-surface placeholder:text-outline focus:outline-none focus:border-vibrant-blue font-semibold"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-deep-navy mb-1">
              Password
            </label>
            <div className="relative">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">
                lock
              </span>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-surface-container-lowest border border-outline-variant/40 rounded-xl pl-10 pr-4 py-2.5 text-xs text-on-surface placeholder:text-outline focus:outline-none focus:border-vibrant-blue font-semibold"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-vibrant-blue hover:bg-vibrant-blue/90 text-white font-bold text-xs py-3 rounded-xl transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer mt-6"
          >
            {loading ? (
              <>
                <span className="material-symbols-outlined animate-spin text-base">sync</span>
                <span>{isSignup ? "Creating Account..." : "Logging In..."}</span>
              </>
            ) : (
              <>
                <span>{isSignup ? "Create Account" : "Log In"}</span>
                <span className="material-symbols-outlined text-base">arrow_forward</span>
              </>
            )}
          </button>
        </form>

        {/* Footer info */}
        <div className="mt-8 text-center text-[10px] text-on-surface-variant font-semibold">
          QueryIQ Enterprise Multi-Tenant Platform &bull; Protected by JWT & Audit Logging
        </div>
      </div>
    </div>
  );
}
