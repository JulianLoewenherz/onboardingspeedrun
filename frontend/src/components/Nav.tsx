"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Onboard" },
  { href: "/history", label: "History" },
  { href: "/settings", label: "Settings" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <header className="border-b bg-white">
      <div className="container mx-auto max-w-3xl px-4 h-14 flex items-center justify-between">
        <span className="font-semibold text-sm tracking-tight">🚀 Onboarding Speedrun</span>
        <nav className="flex gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                pathname === l.href
                  ? "bg-gray-100 text-gray-900"
                  : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
