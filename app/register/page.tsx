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
  CheckCircle2,
  FileCode2,
  Users,
  ArrowRight,
} from "lucide-react";
import { toast } from "sonner";
import { OverBranchLogo } from "@/components/ui/OverBranchLogo";

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
    } catch (err: any) {
      setError(err?.message || "Registration failed. Please try again.");
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

  const isPasswordMatching = password && confirmPassword && password === confirmPassword;

  return (
    <div className="min-h-screen bg-[#00CC68] text-black relative flex flex-col lg:flex-row select-none overflow-x-clip font-sans">
      {/* Left Specimen Panel */}
      <div className="hidden lg:flex lg:w-[45%] bg-black text-white p-12 flex-col justify-between border-r border-black relative z-10 shrink-0">
        <div className="space-y-10">
          <Link href="/" className="inline-flex items-center gap-3">
            <OverBranchLogo size="md" variant="full" colored />
          </Link>

          <div className="space-y-4">
            <div className="font-mono text-xs font-bold text-[#00CC68] tracking-wider uppercase">
              01 // FREE REGISTRATION
            </div>
            <h2 className="font-archivo font-black uppercase text-4xl xl:text-5xl text-white tracking-tight leading-tight">
              CREATE YOUR FREE ACCOUNT.
            </h2>
            <p className="font-sans text-sm text-zinc-400 font-normal leading-relaxed max-w-md">
              Start writing LaTeX with agentic AI assistance, instant compilation vs Overleaf, and unlimited co-authors.
            </p>
          </div>

          {/* Live TeX Code Box */}
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6 font-mono text-xs space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3 text-xs">
              <span className="flex items-center gap-2 font-bold text-white uppercase">
                <FileCode2 className="w-4 h-4 text-[#00CC68]" />
                references.bib
              </span>
              <span className="text-[#00CC68] font-bold text-[11px]">✓ 42 CITATIONS RESOLVED</span>
            </div>

            <div className="space-y-1.5 text-xs text-zinc-300">
              <div className="text-zinc-500">@article&#123;overbranch2026,</div>
              <div className="text-[#00CC68] font-medium pl-4">author = &#123;Vance, Alice and Chen, Bob&#125;,</div>
              <div className="text-zinc-100 pl-4">title = &#123;Agentic LaTeX Document Platform&#125;,</div>
              <div className="text-zinc-400 pl-4">journal = &#123;Academic Software Engineering&#125;, year = &#123;2026&#125;</div>
            </div>

            <div className="pt-3 border-t border-zinc-800 flex items-center justify-between text-[11px] text-zinc-400 font-mono">
              <span className="flex items-center gap-1.5 text-[#00CC68]">
                <Users className="w-3.5 h-3.5" /> UNLIMITED CO-AUTHORS
              </span>
              <span>REALTIME SYNC</span>
            </div>
          </div>

          <ul className="space-y-3 font-sans text-xs text-zinc-300">
            <li className="flex items-center gap-3">
              <CheckCircle2 className="w-4 h-4 text-[#00CC68] shrink-0" />
              <span>Unlimited LaTeX compilation speed compared to Overleaf</span>
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle2 className="w-4 h-4 text-[#00CC68] shrink-0" />
              <span>Agentic AI assistant for document drafting</span>
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle2 className="w-4 h-4 text-[#00CC68] shrink-0" />
              <span>Add unlimited co-authors to every project</span>
            </li>
          </ul>
        </div>

        <div className="pt-8 border-t border-zinc-800 flex items-center justify-between text-xs font-mono text-zinc-500 uppercase">
          <span>OVERBRANCH</span>
          <span>100% FREE & OPEN SOURCE</span>
        </div>
      </div>

      {/* Right Modern Form Container */}
      <div className="flex-1 flex flex-col justify-between p-6 sm:p-10 lg:p-14 relative z-10 min-h-screen overflow-y-auto">
        <div className="flex items-center justify-between max-w-md w-full mx-auto">
          <Link
            href="/"
            className="inline-flex items-center gap-2 bg-black text-white font-mono text-xs font-bold uppercase tracking-wider px-4 py-2 rounded-full hover:bg-white hover:text-black transition-colors shadow-md"
          >
            <ArrowLeft className="w-4 h-4 text-[#00CC68]" />
            <span>BACK TO HOME</span>
          </Link>

          <span className="font-mono text-xs font-bold uppercase tracking-widest text-black/80">
            OVERBRANCH
          </span>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="max-w-md w-full mx-auto my-auto p-8 sm:p-10 bg-white text-zinc-900 rounded-3xl border border-black/10 shadow-2xl space-y-5"
        >
          <div className="space-y-1.5">
            <span className="font-mono text-[11px] font-bold text-[#00CC68] uppercase tracking-wider block">
              LATEX CODE EDITOR
            </span>
            <h1 className="font-archivo font-black uppercase text-3xl text-zinc-950 tracking-tight">
              CREATE ACCOUNT
            </h1>
            <p className="font-sans text-xs sm:text-sm text-zinc-600 leading-relaxed">
              Start writing LaTeX manuscripts with agentic AI and unlimited co-authors.
            </p>
          </div>

          <Button
            variant="outline"
            onClick={handleGoogleSignIn}
            disabled={googleLoading}
            className="w-full h-11 border border-zinc-200 bg-white hover:bg-zinc-50 font-sans text-xs font-semibold rounded-xl flex items-center justify-center gap-3 shadow-xs transition-colors cursor-pointer"
          >
            {googleLoading ? (
              <Loader2 className="w-4 h-4 animate-spin text-zinc-600" />
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

          <div className="relative flex items-center justify-center my-3">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-zinc-200" />
            </div>
            <span className="relative px-3 bg-white font-mono text-[11px] font-medium text-zinc-500 uppercase tracking-wider">
              Or email registration
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-700 font-sans text-xs rounded-xl text-center font-medium">
                {error}
              </div>
            )}

            <div className="space-y-1">
              <Label htmlFor="name" className="font-mono text-xs font-semibold text-zinc-800">
                Full Name
              </Label>
              <div className="relative">
                <Input
                  id="name"
                  type="text"
                  placeholder="Dr. Alex Rivers"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  disabled={loading}
                  className="h-10 pl-10 font-sans text-xs text-zinc-900 border border-zinc-200 bg-zinc-50 focus:bg-white focus:border-[#00CC68] focus:ring-2 focus:ring-[#00CC68]/20 rounded-xl"
                />
                <User className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="email" className="font-mono text-xs font-semibold text-zinc-800">
                Email Address
              </Label>
              <div className="relative">
                <Input
                  id="email"
                  type="email"
                  placeholder="alex@university.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={loading}
                  className="h-10 pl-10 font-sans text-xs text-zinc-900 border border-zinc-200 bg-zinc-50 focus:bg-white focus:border-[#00CC68] focus:ring-2 focus:ring-[#00CC68]/20 rounded-xl"
                />
                <Mail className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="password" className="font-mono text-xs font-semibold text-zinc-800">
                Password
              </Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                  className="h-10 pl-10 pr-10 font-sans text-xs text-zinc-900 border border-zinc-200 bg-zinc-50 focus:bg-white focus:border-[#00CC68] focus:ring-2 focus:ring-[#00CC68]/20 rounded-xl"
                />
                <Lock className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-700"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="font-mono text-[10px] text-zinc-500">Minimum 8 characters</p>
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label htmlFor="confirmPassword" className="font-mono text-xs font-semibold text-zinc-800">
                  Confirm Password
                </Label>
                {isPasswordMatching && (
                  <span className="font-mono text-[10px] text-[#00CC68] font-bold">
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
                  className="h-10 pl-10 font-sans text-xs text-zinc-900 border border-zinc-200 bg-zinc-50 focus:bg-white focus:border-[#00CC68] focus:ring-2 focus:ring-[#00CC68]/20 rounded-xl"
                />
                <Lock className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-12 bg-black text-white hover:bg-[#00CC68] hover:text-black font-mono text-xs font-bold uppercase tracking-wider rounded-full shadow-lg transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-[#00CC68]" />
                  <span>Creating Workspace...</span>
                </>
              ) : (
                <>
                  <span>Create Free Account</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </Button>
          </form>

          <p className="text-center font-sans text-xs text-zinc-600 pt-1">
            Already have an account?{" "}
            <Link href="/login" className="font-bold text-zinc-950 hover:underline">
              Sign in
            </Link>
          </p>
        </motion.div>

        <div className="font-mono text-xs text-center text-black/80 max-w-md mx-auto py-2">
          100% FREE AND OPEN SOURCE
        </div>
      </div>
    </div>
  );
}