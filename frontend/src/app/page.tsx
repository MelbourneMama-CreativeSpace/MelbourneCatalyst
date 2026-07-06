"use client";

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
  BarChart3,
  Brain,
  Globe,
  Layers,
  LineChart,
  MessageSquare,
  Rocket,
  Search,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";

const modules = [
  {
    title: "Company Analyzer",
    description:
      "Deep-dive into any company's digital presence, market positioning, and competitive landscape with AI-powered insights.",
    icon: Search,
    gradient: "from-violet-500 to-purple-600",
    bgGlow: "bg-violet-500/10",
    borderColor: "border-violet-500/20",
    delay: "delay-100",
  },
  {
    title: "Trend Analyzer",
    description:
      "Detect emerging trends before they go mainstream. Leverage real-time data analysis to stay ahead of market shifts.",
    icon: TrendingUp,
    gradient: "from-blue-500 to-cyan-500",
    bgGlow: "bg-blue-500/10",
    borderColor: "border-blue-500/20",
    delay: "delay-200",
  },
  {
    title: "Content Management",
    description:
      "AI-assisted content creation, scheduling, and optimization across all platforms. Maximize engagement effortlessly.",
    icon: MessageSquare,
    gradient: "from-emerald-500 to-teal-500",
    bgGlow: "bg-emerald-500/10",
    borderColor: "border-emerald-500/20",
    delay: "delay-300",
  },
  {
    title: "Social Media Analyzer",
    description:
      "Comprehensive social media analytics with sentiment analysis, audience insights, and performance benchmarking.",
    icon: BarChart3,
    gradient: "from-orange-500 to-rose-500",
    bgGlow: "bg-orange-500/10",
    borderColor: "border-orange-500/20",
    delay: "delay-400",
  },
];

const features = [
  {
    icon: Brain,
    title: "Multi-Agent AI",
    description:
      "Autonomous AI agents that collaborate to deliver comprehensive marketing intelligence.",
  },
  {
    icon: Zap,
    title: "Real-Time Processing",
    description:
      "Lightning-fast data processing with live updates and instant notifications.",
  },
  {
    icon: Globe,
    title: "Global Coverage",
    description:
      "Monitor brands, trends, and conversations across all major platforms worldwide.",
  },
  {
    icon: Layers,
    title: "Modular Architecture",
    description:
      "Plug-and-play modules that scale with your needs. Add capabilities as you grow.",
  },
  {
    icon: LineChart,
    title: "Predictive Analytics",
    description:
      "ML-powered predictions to forecast trends, engagement, and campaign performance.",
  },
  {
    icon: Rocket,
    title: "Automated Workflows",
    description:
      "Set up intelligent automation pipelines that work around the clock for you.",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Background Effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-violet-500/8 rounded-full blur-[120px] pointer-events-none" />
      <div className="fixed bottom-0 right-0 w-[600px] h-[400px] bg-blue-500/6 rounded-full blur-[100px] pointer-events-none" />

      {/* Navigation */}
      <nav className="relative z-50 border-b border-border/50 glass">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold gradient-text">MMCS</span>
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
            <a
              href="#"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Documentation
            </a>
            <Button
              size="sm"
              className="bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 text-white border-0"
            >
              Get Started
            </Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative z-10 pt-24 pb-32 px-6">
        <div className="max-w-7xl mx-auto text-center">
          {/* Badge */}
          <div className="animate-slide-up inline-flex items-center gap-2 px-4 py-2 rounded-full glass mb-8 text-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-muted-foreground">
              AI-Powered Marketing Intelligence Platform
            </span>
          </div>

          {/* Heading */}
          <h1 className="animate-slide-up delay-100 text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-tight mb-6">
            <span className="block">Transform Your</span>
            <span className="block gradient-text">Marketing Strategy</span>
            <span className="block text-foreground/80">With AI Agents</span>
          </h1>

          {/* Subtitle */}
          <p className="animate-slide-up delay-200 max-w-2xl mx-auto text-lg sm:text-xl text-muted-foreground mb-10 leading-relaxed">
            MMCS Social Network combines autonomous AI agents with real-time
            analytics to deliver unparalleled marketing intelligence across
            every channel.
          </p>

          {/* CTA Buttons */}
          <div className="animate-slide-up delay-300 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Button
              size="lg"
              className="bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 text-white border-0 px-8 py-6 text-lg rounded-xl shadow-lg shadow-violet-500/20 hover:shadow-violet-500/40 transition-all"
            >
              Launch Dashboard
              <ArrowRight className="ml-2 w-5 h-5" />
            </Button>
            <Button
              variant="outline"
              size="lg"
              className="px-8 py-6 text-lg rounded-xl border-border/60 hover:bg-accent/50 transition-all"
            >
              View Documentation
            </Button>
          </div>

          {/* Stats */}
          <div className="animate-slide-up delay-500 mt-20 grid grid-cols-2 md:grid-cols-4 gap-8 max-w-3xl mx-auto">
            {[
              { value: "4", label: "AI Modules" },
              { value: "24/7", label: "Monitoring" },
              { value: "100+", label: "Data Sources" },
              { value: "<1s", label: "Response Time" },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-3xl font-bold gradient-text-cool">
                  {stat.value}
                </div>
                <div className="text-sm text-muted-foreground mt-1">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Modules Section */}
      <section id="modules" className="relative z-10 py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Powerful <span className="gradient-text">AI Modules</span>
            </h2>
            <p className="text-muted-foreground max-w-xl mx-auto text-lg">
              Four specialized modules working in harmony to deliver
              comprehensive marketing intelligence.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {modules.map((module) => {
              const IconComponent = module.icon;
              return (
                <Card
                  key={module.title}
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
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span>Active & Ready</span>
                    </div>
                  </CardContent>

                  {/* Shimmer overlay */}
                  <div className="absolute inset-0 animate-shimmer opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="relative z-10 py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Built for <span className="gradient-text-warm">Excellence</span>
            </h2>
            <p className="text-muted-foreground max-w-xl mx-auto text-lg">
              Enterprise-grade features designed to give your marketing team an
              unfair advantage.
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
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-blue-500/20 flex items-center justify-center mb-4 group-hover:from-violet-500/30 group-hover:to-blue-500/30 transition-colors">
                    <IconComponent className="w-5 h-5 text-violet-400" />
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
            <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-violet-500/5 to-blue-500/5 pointer-events-none" />
            <div className="absolute -top-20 -right-20 w-60 h-60 bg-violet-500/10 rounded-full blur-[80px] pointer-events-none animate-float" />
            <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-blue-500/10 rounded-full blur-[80px] pointer-events-none animate-float-delayed" />

            <div className="relative z-10">
              <h2 className="text-3xl sm:text-4xl font-bold mb-4">
                Ready to{" "}
                <span className="gradient-text">Supercharge</span> Your
                Marketing?
              </h2>
              <p className="text-muted-foreground max-w-xl mx-auto mb-8 text-lg">
                Join the next generation of AI-powered marketing intelligence.
                Start analyzing, optimizing, and growing today.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <Button
                  size="lg"
                  className="bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 text-white border-0 px-8 py-6 text-lg rounded-xl shadow-lg shadow-violet-500/20 hover:shadow-violet-500/40 transition-all"
                >
                  Get Started Free
                  <Sparkles className="ml-2 w-5 h-5" />
                </Button>
                <Button
                  variant="outline"
                  size="lg"
                  className="px-8 py-6 text-lg rounded-xl border-border/60 hover:bg-accent/50 transition-all"
                >
                  Schedule Demo
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
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-semibold gradient-text">
              MMCS Social Network
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            © 2026 MMCS Social Network. AI-Powered Marketing Intelligence.
          </p>
        </div>
      </footer>
    </div>
  );
}
