"use client";

import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const supabase = createClient();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm bg-white rounded-xl border shadow-sm p-8">
        <div className="mb-6 text-center">
          <h1 className="text-xl font-bold tracking-tight">Onboarding Speedrun</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to continue</p>
        </div>
        <Auth
          supabaseClient={supabase}
          appearance={{ theme: ThemeSupa }}
          providers={[]}
          redirectTo={`${typeof window !== "undefined" ? window.location.origin : ""}/auth/callback`}
        />
      </div>
    </div>
  );
}
