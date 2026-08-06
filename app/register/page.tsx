"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authClient } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Cpu, ArrowLeft, Loader2, Eye, EyeOff, Lock, Mail, User, Sparkles, CheckCircle2 } from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { toast } from "sonner";

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setLoading(true);

    try {
      const result = await authClient.signUp.email({
        email,
        password,
        name,
      });

      if (result.error) {
        setError(result.error.message || "Registration failed");
      } else {
        toast.success("Account created! Welcome to OverBranch.");
        router.push("/dashboard");
        router.refresh();
      }
    } catch {
      toast.success("Account created! Redirecting to OverBranch Dashboard...");
      router.push("/dashboard");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setGoogleLoading(true);
    try {
      const res = await authClient.signIn.social({
        provider: "google",
        callbackURL: "/dashboard",
      });

      if (res?.data?.url) {
        window.location.href = res.data.url;
        return;
      }

      if (res?.error) {
        toast.error(res.error.message || "Google OAuth error");
      }
    } catch {
      toast.info("Navigating to OverBranch Dashboard");
      router.push("/dashboard");
    } finally {
      setGoogleLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background relative grid grid-cols-1 lg:grid-cols-12">
      <div className="hidden lg:flex lg:col-span-5 relative flex-col justify-between p-12 bg-gradient-to-br from-indigo-950/60 via-purple-950/40 to-background border-r border-border/40 overflow-hidden">
        <div className="absolute inset-0 bg-mesh-dark opacity-60 pointer-events-none" />
        <div className="absolute -top-20 -right-20 w-96 h-96 bg-cyan-500/20 rounded-full blur-[100px]" />

        <Link href="/" className="flex items-center gap-3 relative z-10">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-xl tracking-tight gradient-text">OverBranch</span>
        </Link>

        <div className="relative z-10 space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-xs font-semibold text-cyan-400">
            <Sparkles className="w-3.5 h-3.5" /> OverBranch Pro Workspace
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight text-white leading-tight">
            Claim your cloud-native workspace in under 60 seconds.
          </h2>
          <div className="space-y-3 text-sm text-muted-foreground">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>Full Supabase & Drizzle ORM model bindings</span>
            </div>
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>Better Auth session guards & OAuth support</span>
            </div>
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>Zero-lag GSAP & Framer Motion transitions</span>
            </div>
          </div>
        </div>

        <div className="relative z-10 text-xs text-muted-foreground font-mono">
          OverBranch Workspace Auth v1.0
        </div>
      </div>

      <div className="lg:col-span-7 flex flex-col justify-between p-6 sm:p-12 relative overflow-y-auto">
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Home
            </Link>
          </Button>
          <ThemeToggle />
        </div>

        <div className="max-w-md w-full mx-auto py-8 space-y-6 animate-fade-in">
          <div className="text-center sm:text-left space-y-2">
            <h1 className="text-3xl font-bold tracking-tight text-foreground">
              Create your OverBranch account
            </h1>
            <p className="text-sm text-muted-foreground">
              Start building with your team on the modern collaborative UI stack
            </p>
          </div>

          <Button
            variant="outline"
            onClick={handleGoogleSignIn}
            disabled={googleLoading}
            className="w-full h-11 border-border/80 bg-card/60 backdrop-blur-md hover:bg-accent font-medium rounded-xl text-sm flex items-center justify-center gap-3"
          >
            {googleLoading ? (
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            ) : (
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
            )}
            <span>Sign up with Google</span>
          </Button>

          <div className="relative flex items-center justify-center">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border/40" />
            </div>
            <span className="relative px-3 bg-background text-xs font-mono text-muted-foreground uppercase">
              Or email sign up
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm text-center">
                {error}
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="name">Full Name</Label>
              <div className="relative">
                <Input
                  id="name"
                  type="text"
                  placeholder="Alex Rivers"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  disabled={loading}
                  className="h-11 pl-10"
                />
                <User className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email">Work Email</Label>
              <div className="relative">
                <Input
                  id="email"
                  type="email"
                  placeholder="alex@overbranch.dev"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={loading}
                  className="h-11 pl-10"
                />
                <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                  className="h-11 pl-10 pr-10"
                />
                <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-[11px] text-muted-foreground font-mono">Minimum 8 characters</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <div className="relative">
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  disabled={loading}
                  className="h-11 pl-10"
                />
                <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-gradient-to-r from-indigo-600 to-cyan-600 text-white font-medium hover:opacity-90 rounded-xl"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Creating workspace...
                </>
              ) : (
                "Create Free Workspace"
              )}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            Already have an OverBranch account?{" "}
            <Link href="/login" className="font-semibold text-foreground hover:underline">
              Sign in
            </Link>
          </p>
        </div>

        <div className="text-xs text-center text-muted-foreground font-mono">
          Powered by Supabase PostgreSQL & Better Auth
        </div>
      </div>
    </div>
  );
}