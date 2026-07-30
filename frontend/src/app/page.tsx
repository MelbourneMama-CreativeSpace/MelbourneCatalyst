"use client";

import Image from "next/image";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ArrowRight,
  Brain,
  Globe,
  Layers,
  LineChart,
  MessageSquare,
  Rocket,
  Search,
  Sparkles,
  Zap,
} from "lucide-react";

const modules = [
  {
    title: "Content Studio",
    description:
      "Pick a client, draft this week's captions, and get a strategy, content plan, campaign, and collaboration ideas ready to use — not a spec, a real ready-to-publish draft.",
    icon: MessageSquare,
    gradient: "from-[#00A6A6] to-[#48D7CE]",
    bgGlow: "bg-primary/10",
    borderColor: "border-primary/20",
    delay: "delay-100",
    href: "/companies",
  },
  {
    title: "Add a client",
    description:
      "Onboard a new company from its website — builds the profile Content Studio drafts from.",
    icon: Search,
    gradient: "from-[#071A33] to-[#00A6A6]",
    bgGlow: "bg-accent/10",
    borderColor: "border-accent/20",
    delay: "delay-200",
    href: "/onboarding",
  },
];

// Everything below Content Studio is in development, not part of the
// daily workflow yet — still reachable directly, just not front and
// center on the internal team's homepage.
const inDevelopmentModules = [
  { title: "Trend Analyzer", href: "/trends" },
  { title: "Company research & knowledge base", href: "/companies" },
];

const features = [
  {
    icon: Brain,
    title: "Strategy Consultant",
    description:
      "Generates a marketing strategy, campaign direction, and growth recommendations from a client's profile — reviewable, approve or reject.",
  },
  {
    icon: Zap,
    title: "Content Planner",
    description:
      "Builds a content calendar and drafts real, ready-to-publish captions for every slot — not a brief, copy you can paste and post today.",
  },
  {
    icon: Rocket,
    title: "Campaign Manager",
    description:
      "Turns a content plan into a scheduled campaign with a budget recommendation and lifecycle tracking from draft through archived.",
  },
  {
    icon: Globe,
    title: "Brand Collaboration",
    description:
      "Suggests partnership angles and drafts outreach messages for the kinds of collaborators worth reaching out to.",
  },
  {
    icon: LineChart,
    title: "Analytics",
    description:
      "Not built yet — needs real campaign and engagement data from a connected platform before it can report anything honestly.",
  },
  {
    icon: Layers,
    title: "One workflow per client",
    description:
      "Onboard a client once, then generate strategy → content → campaign → collaboration from that same profile every week.",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Background Effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-primary/8 rounded-full blur-[120px] pointer-events-none" />
      <div className="fixed bottom-0 right-0 w-[600px] h-[400px] bg-accent/6 rounded-full blur-[100px] pointer-events-none" />

      {/* Navigation */}
      <nav className="relative z-50 border-b border-border/50 glass">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Image src="/loomverse-logo.png" alt="LoomVerse AI" width={150} height={36} priority />
          </div>
          <div className="hidden md:flex items-center gap-8">
            <a
              href="#modules"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Modules
            </a>
            <a
              href="#features"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Features
            </a>
            <Link
              href="/companies"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Clients
            </Link>
            <Button
              render={<Link href="/companies" />}
              nativeButton={false}
              size="sm"
              className="bg-gradient-to-r from-primary to-accent hover:opacity-90 text-primary-foreground border-0"
            >
              Open Content Studio
            </Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative z-10 pt-24 pb-32 px-6">
        <div className="max-w-7xl mx-auto text-center">
          {/* Badge */}
          <div className="animate-slide-up inline-flex items-center gap-2 px-4 py-2 rounded-full glass mb-8 text-sm">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-muted-foreground">LoomVerse AI — Content Studio</span>
          </div>

          {/* Heading */}
          <h1 className="animate-slide-up delay-100 text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-tight mb-6">
            <span className="block">This Week&apos;s Captions,</span>
            <span className="block gradient-text">Drafted</span>
          </h1>

          {/* Subtitle */}
          <p className="animate-slide-up delay-200 max-w-2xl mx-auto text-lg sm:text-xl text-muted-foreground mb-10 leading-relaxed">
            Pick a client, generate a content calendar, and get ready-to-publish
            captions for every slot — not a brief, an actual draft you can copy
            and post.
          </p>

          {/* CTA Buttons */}
          <div className="animate-slide-up delay-300 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Button
              render={<Link href="/companies" />}
              nativeButton={false}
              size="lg"
              className="bg-gradient-to-r from-primary to-accent hover:opacity-90 text-primary-foreground border-0 px-8 py-6 text-lg rounded-xl shadow-lg shadow-primary/20 hover:shadow-primary/40 transition-all"
            >
              Open Content Studio
              <ArrowRight className="ml-2 w-5 h-5" />
            </Button>
            <Button
              render={<Link href="/onboarding" />}
              nativeButton={false}
              variant="outline"
              size="lg"
              className="px-8 py-6 text-lg rounded-xl border-border/60 hover:bg-accent/50 transition-all"
            >
              Add a client
            </Button>
          </div>
        </div>
      </section>

      {/* Modules Section */}
      <section id="modules" className="relative z-10 py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Start <span className="gradient-text">here</span>
            </h2>
            <p className="text-muted-foreground max-w-xl mx-auto text-lg">
              Content Studio is the whole tool for now — everything else below is
              still in development.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {modules.map((module) => {
              const IconComponent = module.icon;
              const card = (
                <Card
                  className={`animate-slide-up ${module.delay} group relative overflow-hidden glass border ${module.borderColor} hover-lift cursor-pointer`}
                >
                  {/* Glow effect */}
                  <div
                    className={`absolute inset-0 ${module.bgGlow} opacity-0 group-hover:opacity-100 transition-opacity duration-500`}
                  />

                  <CardHeader className="relative z-10">
                    <div className="flex items-start justify-between">
                      <div
                        className={`w-12 h-12 rounded-xl bg-gradient-to-br ${module.gradient} flex items-center justify-center mb-4 shadow-lg`}
                      >
                        <IconComponent className="w-6 h-6 text-white" />
                      </div>
                      <ArrowRight className="w-5 h-5 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300" />
                    </div>
                    <CardTitle className="text-xl font-semibold">
                      {module.title}
                    </CardTitle>
                    <CardDescription className="text-muted-foreground leading-relaxed">
                      {module.description}
                    </CardDescription>
                  </CardHeader>

                  <CardContent className="relative z-10">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                      <span>Active & Ready</span>
                    </div>
                  </CardContent>

                  {/* Shimmer overlay */}
                  <div className="absolute inset-0 animate-shimmer opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                </Card>
              );

              return module.href ? (
                <Link key={module.title} href={module.href}>
                  {card}
                </Link>
              ) : (
                <div key={module.title}>{card}</div>
              );
            })}
          </div>

          <p className="mt-8 text-center text-sm text-muted-foreground">
            Still in development, reachable directly but not the focus yet:{" "}
            {inDevelopmentModules.map((mod, i) => (
              <span key={mod.title}>
                {i > 0 && ", "}
                <Link href={mod.href} className="underline hover:text-foreground">
                  {mod.title}
                </Link>
              </span>
            ))}
            .
          </p>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="relative z-10 py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              What&apos;s <span className="gradient-text-warm">live today</span>
            </h2>
            <p className="text-muted-foreground max-w-xl mx-auto text-lg">
              Content Studio&apos;s five agents — what each one actually does right now.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature, index) => {
              const IconComponent = feature.icon;
              return (
                <div
                  key={feature.title}
                  className="animate-slide-up group p-6 rounded-2xl glass hover-lift cursor-pointer"
                  style={{ animationDelay: `${(index + 1) * 100}ms` }}
                >
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center mb-4 group-hover:from-primary/30 group-hover:to-accent/30 transition-colors">
                    <IconComponent className="w-5 h-5 text-primary" />
                  </div>
                  <h3 className="text-lg font-semibold mb-2">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {feature.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative z-10 py-24 px-6">
        <div className="max-w-4xl mx-auto">
          <div className="relative overflow-hidden rounded-3xl glass-strong p-12 text-center">
            {/* Background decoration */}
            <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-primary/5 to-accent/5 pointer-events-none" />
            <div className="absolute -top-20 -right-20 w-60 h-60 bg-primary/10 rounded-full blur-[80px] pointer-events-none animate-float" />
            <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-accent/10 rounded-full blur-[80px] pointer-events-none animate-float-delayed" />

            <div className="relative z-10">
              <h2 className="text-3xl sm:text-4xl font-bold mb-4">
                This week&apos;s calendar,{" "}
                <span className="gradient-text">drafted</span>
              </h2>
              <p className="text-muted-foreground max-w-xl mx-auto mb-8 text-lg">
                Open a client you&apos;re already working with, or onboard a new one.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <Button
                  render={<Link href="/companies" />}
                  nativeButton={false}
                  size="lg"
                  className="bg-gradient-to-r from-primary to-accent hover:opacity-90 text-primary-foreground border-0 px-8 py-6 text-lg rounded-xl shadow-lg shadow-primary/20 hover:shadow-primary/40 transition-all"
                >
                  Open Content Studio
                  <Sparkles className="ml-2 w-5 h-5" />
                </Button>
                <Button
                  render={<Link href="/onboarding" />}
                  nativeButton={false}
                  variant="outline"
                  size="lg"
                  className="px-8 py-6 text-lg rounded-xl border-border/60 hover:bg-accent/50 transition-all"
                >
                  Add a client
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border/50 py-12 px-6">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Image src="/loomverse-mark.png" alt="LoomVerse AI" width={24} height={24} />
            <span className="font-semibold gradient-text">
              LoomVerse AI — Content Studio
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            Internal tool — MMCS team use.
          </p>
        </div>
      </footer>
    </div>
  );
}
