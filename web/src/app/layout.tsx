import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { SITE } from "@/lib/data";

export const metadata: Metadata = {
  title: "Lead Research Pipeline",
  description:
    "A working demo: small companies in the North East of England found, checked against their websites and scored as sales leads by an AI pipeline.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/leads", label: "Leads" },
  { href: "/pipeline", label: "Pipeline and data quality" },
  { href: "/evaluation", label: "How accurate is it?" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <header className="border-b border-hairline bg-surface">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
            <Link href="/" className="font-semibold text-ink">
              Lead Research Pipeline
            </Link>
            <nav className="flex flex-wrap gap-1 text-sm">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-md px-2.5 py-1.5 text-ink-2 hover:bg-accent-wash hover:text-ink"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">{children}</main>
        <footer className="border-t border-hairline bg-surface">
          <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-2 px-4 py-5 text-sm text-ink-3 sm:px-6">
            <span>Company-level public data only. CRM data is synthetic.</span>
            <span className="flex gap-4">
              <a href={SITE.githubUrl} className="hover:text-ink">Source code</a>
              <a href={SITE.contactUrl} className="hover:text-ink">{SITE.contactLabel}</a>
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
