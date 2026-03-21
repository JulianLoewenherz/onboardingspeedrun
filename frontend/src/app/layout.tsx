import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import Nav from "@/components/Nav";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });

export const metadata: Metadata = {
  title: "Onboarding Speedrun",
  description: "Onboard new hires across Notion, GitHub, Slack, and Gmail in seconds.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-gray-50 text-gray-900">
        <Nav />
        <main className="flex-1 container mx-auto max-w-3xl px-4 py-10">
          {children}
        </main>
        <Toaster />
      </body>
    </html>
  );
}
