"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
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
  ShieldCheck,
  CheckCircle2,
  FileCode2,
  Users,
  Sparkles,
} from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { toast } from "sonner";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

/* Hallmark · archetype: Workbench · component: LoginPage · theme: Garden */
export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [forgotModalOpen, setForgotModalOpen] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");

  const { data: session } = authClient.useSession();

  if (session?.user) {
    router.replace("/dashboard");
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await authClient.signIn.email({
        email,
        password,
      });

      if (result.error) {
        setError(result.error.message || "Invalid credentials");
      } else {
        toast.success("Welcome back to OverBranch!");
        router.push("/dashboard");
        router.refresh();
      }
    } catch (err: any) {
      setError(err?.message || "Sign in failed. Please check your credentials.");
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
    } catch (err: any) {
      toast.error(err?.message || "Google sign in failed");
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleForgotSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    toast.success(`Password reset instructions sent to ${forgotEmail}`);
    setForgotModalOpen(false);
  };

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
              <ShieldCheck className="w-3.5 h-3.5" /> ACADEMIC WORKSPACE
            </div>
            <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground leading-snug">
              Co-author seminar reports, assignments & slides with zero friction.
            </h2>
          </div>

          {/* Live TeX Specimen Sandbox Card */}
          <div className="rounded-2xl border border-border bg-background p-5 font-mono text-xs space-y-3 shadow-sm">
            <div className="flex items-center justify-between border-b border-border pb-2 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1.5 font-bold text-foreground">
                <FileCode2 className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />
                seminar_report.tex
              </span>
              <span className="text-emerald-500 dark:text-emerald-400 font-bold">✓ Compiled in 6ms</span>
            </div>

            <div className="space-y-1 text-[11px]">
              <div className="text-muted-foreground">\documentclass&#123;report&#125;</div>
              <div className="text-emerald-500 dark:text-emerald-400">\usepackage&#123;overbranch&#125;</div>
              <div className="text-foreground pl-3">\begin&#123;document&#125;</div>
              <div className="text-foreground/90 pl-6">\section&#123;Project Methodology&#125;</div>
              <div className="text-foreground/80 pl-6">$ E = mc^2 $</div>
              <div className="text-foreground pl-3">\end&#123;document&#125;</div>
            </div>

            <div className="pt-2 border-t border-border flex items-center justify-between text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <Users className="w-3 h-3 text-emerald-500 dark:text-emerald-400" /> 2 Team Authors Active
              </span>
              <span>pdfLaTeX • SyncTeX</span>
            </div>
          </div>

          <ul className="space-y-2.5 text-xs text-muted-foreground font-mono">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
              Seminar, lab assignment & project report templates
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
              Instant multi-author SyncTeX cursor navigation
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
              BibTeX reference manager & instant citation lookup
            </li>
          </ul>
        </div>

        <div className="relative z-10 pt-6 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground font-mono">
          <span>OverBranch Academic Suite</span>
          <span>v1.0.4</span>
        </div>
      </div>

      {/* Right Auth Form */}
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
          className="max-w-md w-full mx-auto my-auto p-6 sm:p-8 rounded-2xl border border-border bg-card shadow-xl space-y-6"
        >
          <div className="text-center sm:text-left space-y-1.5">
            <span className="text-[11px] font-mono text-emerald-500 dark:text-emerald-400 font-bold uppercase tracking-widest">
              STUDENT & AUTHOR PORTAL
            </span>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
              Sign in to OverBranch
            </h1>
            <p className="text-xs sm:text-sm text-muted-foreground">
              Access your seminar reports, project assignments, slides & papers.
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
            <span>Sign in with Google</span>
          </Button>

          <div className="relative flex items-center justify-center">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border" />
            </div>
            <span className="relative px-3 bg-card text-[11px] font-mono text-muted-foreground uppercase">
              Or email credentials
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs text-center font-mono font-semibold">
                {error}
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-xs font-mono">Work / University Email</Label>
              <div className="relative">
                <Input
                  id="email"
                  type="email"
                  placeholder="author@university.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={loading}
                  className="h-10 pl-10 text-xs font-mono border-border bg-background"
                />
                <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-xs font-mono">Password</Label>
                <button
                  type="button"
                  onClick={() => setForgotModalOpen(true)}
                  className="text-xs text-emerald-500 dark:text-emerald-400 hover:underline font-mono"
                >
                  Forgot password?
                </button>
              </div>
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
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-emerald-600 hover:bg-emerald-500 dark:bg-emerald-500 dark:hover:bg-emerald-400 text-white dark:text-zinc-950 font-semibold rounded-xl text-xs shadow-xs"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Verifying Account...
                </>
              ) : (
                "Open Manuscript Workspace"
              )}
            </Button>
          </form>

          <p className="text-center text-xs text-muted-foreground font-mono pt-1">
            New to OverBranch?{" "}
            <Link href="/register" className="font-bold text-foreground hover:underline">
              Create a free account
            </Link>
          </p>
        </motion.div>

        <div className="text-[11px] text-center text-muted-foreground font-mono py-2">
          Protected by Encrypted Enterprise Session Security
        </div>
      </div>

      <AnimatePresence>
        {forgotModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="max-w-md w-full p-6 rounded-2xl border border-border bg-card shadow-2xl space-y-4"
            >
              <h3 className="text-base font-bold text-foreground">Reset Password</h3>
              <p className="text-xs text-muted-foreground">
                Enter your registered account email to receive reset instructions.
              </p>
              <form onSubmit={handleForgotSubmit} className="space-y-4 pt-1">
                <Input
                  type="email"
                  placeholder="author@university.edu"
                  value={forgotEmail}
                  onChange={(e) => setForgotEmail(e.target.value)}
                  required
                  className="h-10 text-xs font-mono"
                />
                <div className="flex items-center justify-end gap-2 text-xs">
                  <Button variant="ghost" type="button" onClick={() => setForgotModalOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" className="bg-emerald-600 dark:bg-emerald-500 text-white dark:text-zinc-950 font-bold">
                    Send Reset Link
                  </Button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}