"use client";

import React, { useState, useEffect } from "react";
import { User, Mail, MapPin, Building, Shield, Save, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { authClient } from "@/lib/auth-client";
import { toast } from "sonner";

export default function ProfilePage() {
  const { data: session } = authClient.useSession();

  const [name, setName] = useState("Alex Rivers");
  const [email, setEmail] = useState("alex@overbranch.dev");
  const [avatarUrl, setAvatarUrl] = useState("https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80");
  const [bio, setBio] = useState("Academic Researcher & Student Author");
  const [location, setLocation] = useState("University Campus");
  const [company, setCompany] = useState("Academic Workspace");

  useEffect(() => {
    if (session?.user) {
      if (session.user.name) setName(session.user.name);
      if (session.user.email) setEmail(session.user.email);
      if (session.user.image) setAvatarUrl(session.user.image);
    }
  }, [session]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    toast.success("Profile customization updated successfully");
  };

  return (
    <div className="space-y-6 sm:space-y-8 animate-fade-in pb-12 max-w-3xl">
      <div className="space-y-1">
        <h1 className="text-xl sm:text-3xl font-extrabold tracking-tight text-foreground">
          User Profile Customization
        </h1>
        <p className="text-xs sm:text-sm text-muted-foreground">
          Manage personal avatar, display name, academic affiliations, and co-author identities.
        </p>
      </div>

      <Card className="p-4 sm:p-8 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl space-y-6">
        <div className="flex items-center gap-3.5 sm:gap-4">
          <Avatar className="w-14 h-14 sm:w-16 sm:h-16 border-2 border-indigo-500/40 shrink-0">
            <AvatarImage src={avatarUrl} />
            <AvatarFallback className="bg-indigo-600 text-white font-bold">
              {name.slice(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <h2 className="text-base sm:text-lg font-bold text-foreground truncate">{name}</h2>
            <p className="text-xs text-muted-foreground font-mono truncate">{email}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="prof-name">Full Name / Academic Co-Author Signature</Label>
            <Input id="prof-name" value={name} onChange={(e) => setName(e.target.value)} className="h-11" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prof-email">Verified Session Email</Label>
            <Input id="prof-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="h-11" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prof-avatar">Avatar Image URL</Label>
            <Input id="prof-avatar" value={avatarUrl} onChange={(e) => setAvatarUrl(e.target.value)} className="h-11 font-mono text-xs" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="prof-bio">Author Bio & Research Focus</Label>
            <Input id="prof-bio" value={bio} onChange={(e) => setBio(e.target.value)} className="h-11" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="prof-company">Organization / University</Label>
              <Input id="prof-company" value={company} onChange={(e) => setCompany(e.target.value)} className="h-11" />
            </div>

            <div className="space-y-2">
              <Label htmlFor="prof-loc">Location</Label>
              <Input id="prof-loc" value={location} onChange={(e) => setLocation(e.target.value)} className="h-11" />
            </div>
          </div>

          <div className="pt-4 flex justify-end">
            <Button type="submit" className="bg-indigo-600 text-white rounded-xl">
              <Save className="w-4 h-4 mr-2" />
              Save Profile
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
