"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Cpu, ArrowLeft, Loader2, Mail, CheckCircle2 } from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { toast } from "sonner";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setSubmitted(true);
      toast.success(`Password reset link sent to ${email}`);
    }, 1000);
  };

  return (
    <div className="min-h-screen bg-background relative grid grid-cols-1 lg:grid-cols-12">
      <div className="hidden lg:flex lg:col-span-5 relative flex-col justify-between p-12 bg-gradient-to-br from-indigo-950/60 via-purple-950/40 to-background border-r border-border/40 overflow-hidden">
        <div className="absolute inset-0 bg-mesh-dark opacity-60 pointer-events-none" />
        <div className="absolute -bottom-20 -left-20 w-96 h-96 bg-indigo-500/20 rounded-full blur-[100px]" />

        <Link href="/" className="flex items-center gap-3 relative z-10">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-xl tracking-tight gradient-text">OverBranch</span>
        </Link>

        <div className="relative z-10 space-y-4">
          <h2 className="text-3xl font-extrabold tracking-tight text-white leading-tight">
            Account Security & Password Recovery
          </h2>
          <p className="text-sm text-muted-foreground">
            Enter your verified work email address to receive password reset instructions.
          </p>
        </div>

        <div className="relative z-10 text-xs text-muted-foreground font-mono">
          Better Auth Protocol
        </div>
      </div>

      <div className="lg:col-span-7 flex flex-col justify-between p-6 sm:p-12 relative">
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/login">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Login
            </Link>
          </Button>
          <ThemeToggle />
        </div>

        <div className="max-w-md w-full mx-auto py-12 space-y-6 animate-fade-in">
          {submitted ? (
            <div className="text-center space-y-4 p-8 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl">
              <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mx-auto flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h1 className="text-2xl font-bold text-foreground">Reset Link Dispatched</h1>
              <p className="text-sm text-muted-foreground">
                We sent password recovery instructions to <strong className="text-foreground">{email}</strong>.
              </p>
              <Button asChild className="w-full bg-indigo-600 text-white rounded-xl">
                <Link href="/login">Return to Sign In</Link>
              </Button>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-foreground">Forgot Password</h1>
                <p className="text-sm text-muted-foreground">
                  No worries! Enter your registered account email and we will send a reset link.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Work Email</Label>
                  <div className="relative">
                    <Input
                      id="email"
                      type="email"
                      placeholder="developer@overbranch.dev"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      disabled={loading}
                      className="h-11 pl-10"
                    />
                    <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={loading}
                  className="w-full h-11 bg-gradient-to-r from-indigo-600 to-cyan-600 text-white font-medium hover:opacity-90 rounded-xl"
                >
                  {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : "Send Reset Instructions"}
                </Button>
              </form>
            </>
          )}
        </div>

        <div className="text-xs text-center text-muted-foreground font-mono">
          Protected by Better Auth
        </div>
      </div>
    </div>
  );
}
