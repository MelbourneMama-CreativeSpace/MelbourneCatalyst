import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "LoomVerse AI",
  description:
    "LoomVerse AI's Content Studio — drafting weekly client content: strategy, a content calendar with ready-to-publish captions, campaigns, and collaboration ideas.",
  keywords: ["LoomVerse AI", "content studio", "content calendar", "content drafting"],
  icons: { icon: "/loomverse-mark.png" },
};

// Deliberately minimal — no auth-aware chrome here. The landing page (`/`)
// and `/login` are public, so a global sign-out control doesn't belong at
// this level; the dashboard shell (`(dashboard)/layout.tsx`) owns that.
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} font-sans antialiased bg-background text-foreground`}
      >
        {children}
      </body>
    </html>
  );
}
