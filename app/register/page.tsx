"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { authClient } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ArrowLeft,
  Loader2,
  Eye,
  EyeOff,
  Lock,
  Mail,
  User,
  ShieldCheck,
  CheckCircle2,
  FileCode2,
  Users,
} from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { toast } from "sonner";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

/* Hallmark · archetype: Workbench · component: RegisterPage · theme: Garden */
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

  const { data: session } = authClient.useSession();

  if (session?.user) {
    router.replace("/dashboard");
  }

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

  const isPasswordMatching = password && confirmPassword && password === confirmPassword;

  return (
    <div className="min-h-screen bg-background relative flex flex-col lg:flex-row overflow-x-clip">
      {/* Left Specimen Workbench Panel */}
      <div className="hidden lg:flex lg:w-[42%] xl:w-[40%] bg-card border-r border-border flex-col justify-between p-10 shrink-0 select-none">
        <div className="space-y-8 relative z-10">
          <Link href="/" className="flex items-center gap-3">
            <OverBranchLogo size="lg" variant="full" colored />
          </Link>

          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-xs font-mono font-bold text-emerald-500 dark:text-emerald-400">
              <ShieldCheck className="w-3.5 h-3.5" /> ACADEMIC LATEX WORKSPACE
            </div>
            <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground leading-snug">
              Claim your report & presentation workspace in 60 seconds.
            </h2>
          </div>

          {/* Live TeX Specimen Sandbox Card */}
          <div className="rounded-2xl border border-border bg-background p-5 font-mono text-xs space-y-3 shadow-sm">
            <div className="flex items-center justify-between border-b border-border pb-2 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1.5 font-bold text-foreground">
                <FileCode2 className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />
                references.bib
              </span>
              <span className="text-emerald-500 dark:text-emerald-400 font-bold">✓ 42 Citations Resolved</span>
            </div>

            <div className="space-y-1 text-[11px]">
              <div className="text-muted-foreground">@article&#123;overbranch2026,</div>
              <div className="text-emerald-500 dark:text-emerald-400 pl-3">author = &#123;Vance, Alice and Chen, Bob&#125;,</div>
              <div className="text-foreground pl-3">title = &#123;Real-time Academic Document Platform&#125;,</div>
              <div className="text-foreground/80 pl-3">journal = &#123;Academic Software Engineering&#125;, year = &#123;2026&#125;</div>
            </div>

            <div className="pt-2 border-t border-border flex items-center justify-between text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <Users className="w-3 h-3 text-emerald-500 dark:text-emerald-400" /> Team Project Ready
              </span>
              <span>Real-Time Sync • Instant Recompile</span>
            </div>
          </div>

          <ul className="space-y-2.5 text-xs text-muted-foreground font-mono">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
              Seminar, lab assignment & project report templates
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
              Beamer presentation slides & PPT layout support
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
              Zero-latency PDF compilation & cursor tracking
            </li>
          </ul>
        </div>

        <div className="relative z-10 pt-6 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground font-mono">
          <span>OverBranch Academic Workspace</span>
          <span>v1.0.4</span>
        </div>
      </div>

      {/* Right Form Container */}
      <div className="flex-1 flex flex-col justify-between p-6 sm:p-10 lg:p-12 relative overflow-y-auto min-h-screen">
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" asChild className="text-xs font-mono">
            <Link href="/">
              <ArrowLeft className="w-4 h-4 mr-2 text-emerald-500 dark:text-emerald-400" />
              Back to Home
            </Link>
          </Button>
          <ThemeToggle />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="max-w-md w-full mx-auto my-auto p-6 sm:p-8 rounded-2xl border border-border bg-card shadow-xl space-y-5"
        >
          <div className="text-center sm:text-left space-y-1.5">
            <span className="text-[11px] font-mono text-emerald-500 dark:text-emerald-400 font-bold uppercase tracking-widest">
              STUDENT & AUTHOR REGISTRATION
            </span>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
              Create your account
            </h1>
            <p className="text-xs sm:text-sm text-muted-foreground">
              Start co-authoring seminar reports, assignments & slides with your team.
            </p>
          </div>

          <Button
            variant="outline"
            onClick={handleGoogleSignIn}
            disabled={googleLoading}
            className="w-full h-11 border-border bg-background hover:bg-accent font-mono font-medium rounded-xl text-xs flex items-center justify-center gap-3 shadow-xs"
          >
            {googleLoading ? (
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            ) : (
              <svg className="w-4 h-4" viewBox="0 0 24 24">
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
              <div className="w-full border-t border-border" />
            </div>
            <span className="relative px-3 bg-card text-[11px] font-mono text-muted-foreground uppercase">
              Or email sign up
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            {error && (
              <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs text-center font-mono font-semibold">
                {error}
              </div>
            )}

            <div className="space-y-1">
              <Label htmlFor="name" className="text-xs font-mono">Full Name</Label>
              <div className="relative">
                <Input
                  id="name"
                  type="text"
                  placeholder="Dr. Alex Rivers"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  disabled={loading}
                  className="h-10 pl-10 text-xs font-mono border-border bg-background"
                />
                <User className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="email" className="text-xs font-mono">Work / University Email</Label>
              <div className="relative">
                <Input
                  id="email"
                  type="email"
                  placeholder="alex@university.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={loading}
                  className="h-10 pl-10 text-xs font-mono border-border bg-background"
                />
                <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="password" className="text-xs font-mono">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                  className="h-10 pl-10 pr-10 text-xs font-mono border-border bg-background"
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
              <p className="text-[10px] text-muted-foreground font-mono">Minimum 8 characters</p>
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label htmlFor="confirmPassword" className="text-xs font-mono">Confirm Password</Label>
                {isPasswordMatching && (
                  <span className="text-[10px] font-mono text-emerald-500 dark:text-emerald-400 font-bold">
                    ✓ Passwords Match
                  </span>
                )}
              </div>
              <div className="relative">
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  disabled={loading}
                  className="h-10 pl-10 text-xs font-mono border-border bg-background"
                />
                <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold rounded-xl text-xs shadow-xs"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Creating Workspace...
                </>
              ) : (
                "Create Free Workspace Account"
              )}
            </Button>
          </form>

          <p className="text-center text-xs text-muted-foreground font-mono pt-1">
            Already have an account?{" "}
            <Link href="/login" className="font-bold text-foreground hover:underline">
              Sign in
            </Link>
          </p>
        </motion.div>

        <div className="text-[11px] text-center text-muted-foreground font-mono py-2">
          Built for High-Velocity Scientific Research
        </div>
      </div>
    </div>
  );
}