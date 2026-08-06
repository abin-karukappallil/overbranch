"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Cpu, Lock, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      toast.success("Password reset successfully!");
      router.push("/login");
    }, 1000);
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 relative">
      <div className="max-w-md w-full p-8 rounded-2xl border border-border/80 bg-card/70 backdrop-blur-2xl shadow-2xl space-y-6">
        <div className="text-center space-y-2">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 mx-auto flex items-center justify-center shadow-lg">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-foreground">Set New Password</h1>
          <p className="text-sm text-muted-foreground">
            Choose a strong new password for your OverBranch account.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="password">New Password</Label>
            <div className="relative">
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loading}
                className="h-11 pl-10"
              />
              <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirm New Password</Label>
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
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : "Update Password"}
          </Button>
        </form>
      </div>
    </div>
  );
}
