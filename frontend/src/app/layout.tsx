import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "MMCS Social Network | AI-Powered Marketing Intelligence",
  description:
    "MMCS Social Network is an AI-powered marketing intelligence platform featuring Company Analyzer, Trend Analyzer, Content Management, and Social Media Analyzer modules to supercharge your marketing strategy.",
  keywords: [
    "AI marketing",
    "social media analytics",
    "trend analysis",
    "content management",
    "company analyzer",
    "marketing intelligence",
  ],
};

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
