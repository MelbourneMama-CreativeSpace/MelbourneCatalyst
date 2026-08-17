"use client";

import Link from "next/link";
import {
  BarChart3,
  Bot,
  Brain,
  Calendar,
  Check,
  ChevronRight,
  Globe,
  LineChart,
  Rocket,
  Search,
  Shield,
  Sparkles,
  Star,
  TrendingUp,
} from "lucide-react";

/* ─────────────────────────────────────────────
   DATA
───────────────────────────────────────────── */

const navLinks = [
  { label: "Features", href: "#features" },
  { label: "Process", href: "#process" },
  { label: "Testimonials", href: "#testimonials" },
  { label: "Pricing", href: "#pricing" },
  { label: "Blog", href: "#blog" },
];

const features = [
  {
    icon: Brain,
    title: "Strategy Consultant",
    description:
      "Generates a full marketing strategy from a client's profile — aligned to their goals, brand voice, and market position.",
  },
  {
    icon: Calendar,
    title: "Content Planner",
    description:
      "Builds a multi-week content calendar with ready-to-publish captions for every slot — not a brief, real copy.",
  },
  {
    icon: Rocket,
    title: "Campaign Manager",
    description:
      "Turns content plans into structured campaigns with budgets, timelines, and lifecycle tracking.",
  },
  {
    icon: Globe,
    title: "Brand Collaboration",
    description:
      "Identifies relevant partnership angles and drafts outreach messages for collaborators worth reaching.",
  },
  {
    icon: TrendingUp,
    title: "Trend Analyzer",
    description:
      "Continuously tracks rising search terms, Reddit discussions, YouTube trends, and news to surface what matters to your niche.",
  },
  {
    icon: BarChart3,
    title: "Analytics Engine",
    description:
      "Connects social platforms via Composio to monitor real-time performance — follower growth, engagement, impressions.",
  },
];

const steps = [
  {
    number: "01",
    title: "Onboard a Company",
    description:
      "Enter a website URL. Our AI crawls it, extracts the brand, products, audience, and voice — building a full knowledge base automatically.",
    icon: Search,
  },
  {
    number: "02",
    title: "AI Runs the Analysis",
    description:
      "Multiple specialised agents analyse competitors, discover trending topics, and score relevance to the company's niche.",
    icon: Bot,
  },
  {
    number: "03",
    title: "Generate Content",
    description:
      "In one click, get a strategy, content calendar, campaigns, and collaboration ideas — all grounded in real data, not templates.",
    icon: Sparkles,
  },
  {
    number: "04",
    title: "Monitor & Improve",
    description:
      "Connect social accounts, track performance across platforms, and let every campaign make the system smarter.",
    icon: LineChart,
  },
];

const testimonials = [
  {
    quote:
      "LoomVerse AI cut our content planning from a full day to under an hour. The strategy agent genuinely understands our brand.",
    author: "Sarah Chen",
    role: "Head of Marketing, Nexora",
    avatar: "SC",
  },
  {
    quote:
      "The trend analyzer alone is worth it. We pivoted our entire Q3 campaign based on signals it surfaced two weeks before anyone else noticed.",
    author: "Marcus Williams",
    role: "Founder, Apex Digital",
    avatar: "MW",
  },
  {
    quote:
      "Finally, an AI tool that produces actual copy we can use, not bullet-point outlines we still have to write ourselves.",
    author: "Priya Sharma",
    role: "Content Director, BrightLeaf",
    avatar: "PS",
  },
];

const pricingPlans = [
  {
    name: "Starter",
    price: "$49",
    period: "/month",
    description: "Perfect for freelancers managing a handful of clients.",
    features: [
      "Up to 5 client companies",
      "Content Studio (Strategy + Planner)",
      "Google Trends integration",
      "7-day trend history",
      "Email support",
    ],
    cta: "Get Started",
    highlighted: false,
  },
  {
    name: "Pro",
    price: "$149",
    period: "/month",
    description: "For agencies ready to scale their content output.",
    features: [
      "Up to 25 client companies",
      "Full Content Studio suite",
      "All trend sources (Reddit, YouTube, X)",
      "Social media platform connections",
      "Campaign Manager + Brand Collab",
      "Knowledge Base + Competitor Research",
      "Priority support",
    ],
    cta: "Start Free Trial",
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "Dedicated infrastructure for large teams.",
    features: [
      "Unlimited companies",
      "Custom agent configuration",
      "White-label option",
      "Dedicated success manager",
      "SLA guarantee",
      "Custom integrations",
    ],
    cta: "Contact Sales",
    highlighted: false,
  },
];

const stats = [
  { value: "10×", label: "Faster content creation" },
  { value: "500+", label: "Agencies onboarded" },
  { value: "98%", label: "Strategy accuracy score" },
  { value: "40hrs", label: "Saved per client / month" },
];

/* ─────────────────────────────────────────────
   COMPONENT
───────────────────────────────────────────── */

export default function LandingPage() {
  return (
    <div className="lv-page">
      {/* ── NAV ── */}
      <nav className="lv-nav">
        <div className="lv-nav-inner">
          {/* Logo */}
          <Link href="/" className="lv-logo">
            <span className="lv-logo-icon">
              <Sparkles size={16} />
            </span>
            <span className="lv-logo-text">LoomVerse AI</span>
          </Link>

          {/* Links */}
          <ul className="lv-nav-links">
            {navLinks.map((l) => (
              <li key={l.label}>
                <a href={l.href} className="lv-nav-link">
                  {l.label}
                </a>
              </li>
            ))}
          </ul>

          {/* Actions */}
          <div className="lv-nav-actions">
            <Link href="/login" className="lv-btn-ghost">
              Login
            </Link>
            <Link href="/login" className="lv-btn-primary">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="lv-hero">
        {/* soft gradient blobs */}
        <div className="lv-blob lv-blob-1" />
        <div className="lv-blob lv-blob-2" />
        <div className="lv-blob lv-blob-3" />

        <div className="lv-hero-content">
          {/* Badge */}
          <div className="lv-badge">
            <Sparkles size={12} className="lv-badge-icon" />
            <span>AI-POWERED MARKETING INTELLIGENCE</span>
          </div>

          {/* Headline */}
          <h1 className="lv-hero-h1">
            The AI Agent Platform for
            <br />
            <span className="lv-teal-text">Modern Marketing Teams</span>
          </h1>

          {/* Sub */}
          <p className="lv-hero-sub">
            LoomVerse AI helps you connect, manage, and automate your entire
            content pipeline effortlessly. Unlock powerful insights and produce
            ready-to-publish content with ease.
          </p>

          {/* CTAs */}
          <div className="lv-hero-ctas">
            <Link href="/login" className="lv-btn-dark">
              Get Started
            </Link>
            <Link href="#features" className="lv-btn-outline">
              Book a Demo
            </Link>
          </div>
        </div>

        {/* Dashboard preview card */}
        <div className="lv-hero-preview">
          <div className="lv-preview-card">
            {/* Mock header */}
            <div className="lv-preview-header">
              <div className="lv-preview-dots">
                <span /><span /><span />
              </div>
              <span className="lv-preview-url">loomverse.ai / dashboard</span>
            </div>

            {/* Mock content */}
            <div className="lv-preview-body">
              <div className="lv-preview-sidebar">
                {["Dashboard","Companies","Trends","Content","Analytics"].map((item) => (
                  <div key={item} className="lv-preview-sidebar-item">
                    <span className="lv-preview-dot" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
              <div className="lv-preview-main">
                <div className="lv-preview-stat-row">
                  {[
                    { label: "Active Clients", val: "24" },
                    { label: "Trends Today", val: "138" },
                    { label: "Campaigns", val: "12" },
                  ].map((s) => (
                    <div key={s.label} className="lv-preview-stat">
                      <span className="lv-preview-stat-val">{s.val}</span>
                      <span className="lv-preview-stat-label">{s.label}</span>
                    </div>
                  ))}
                </div>
                <div className="lv-preview-chart">
                  {[40, 65, 50, 80, 70, 90, 75].map((h, i) => (
                    <div
                      key={i}
                      className="lv-preview-bar"
                      style={{ height: `${h}%` }}
                    />
                  ))}
                </div>
                <div className="lv-preview-feed">
                  {["Strategy generated — Apex Digital","Trend detected: AI video marketing","Campaign launched — BrightLeaf Q3"].map((t) => (
                    <div key={t} className="lv-preview-feed-item">
                      <span className="lv-preview-feed-dot" />
                      <span>{t}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
          {/* Floating badge */}
          <div className="lv-float-badge lv-float-badge-1">
            <TrendingUp size={14} />
            <span>+138 Trends collected</span>
          </div>
          <div className="lv-float-badge lv-float-badge-2">
            <Check size={14} />
            <span>Strategy ready</span>
          </div>
        </div>
      </section>

      {/* ── STATS ── */}
      <section className="lv-stats-band">
        {stats.map((s) => (
          <div key={s.label} className="lv-stat-item">
            <span className="lv-stat-val">{s.value}</span>
            <span className="lv-stat-label">{s.label}</span>
          </div>
        ))}
      </section>

      {/* ── FEATURES ── */}
      <section id="features" className="lv-section">
        <div className="lv-section-inner">
          <div className="lv-section-head">
            <div className="lv-section-badge">Features</div>
            <h2 className="lv-section-h2">
              Every tool your agency needs,<br />
              <span className="lv-teal-text">in one intelligent platform</span>
            </h2>
            <p className="lv-section-sub">
              Six specialised AI agents work together so you never start from a
              blank page again.
            </p>
          </div>

          <div className="lv-features-grid">
            {features.map((f, i) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="lv-feature-card" style={{ animationDelay: `${i * 80}ms` }}>
                  <div className="lv-feature-icon">
                    <Icon size={22} />
                  </div>
                  <h3 className="lv-feature-title">{f.title}</h3>
                  <p className="lv-feature-desc">{f.description}</p>
                  <div className="lv-feature-arrow">
                    <ChevronRight size={16} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── PROCESS ── */}
      <section id="process" className="lv-section lv-section-navy">
        <div className="lv-section-inner">
          <div className="lv-section-head">
            <div className="lv-section-badge lv-section-badge-light">Process</div>
            <h2 className="lv-section-h2 lv-h2-light">
              From website URL to published content
              <span className="lv-aqua-text"> in four steps</span>
            </h2>
            <p className="lv-section-sub lv-sub-light">
              A continuous learning cycle that improves every campaign.
            </p>
          </div>

          <div className="lv-steps-grid">
            {steps.map((step, i) => {
              const Icon = step.icon;
              return (
                <div key={step.number} className="lv-step-card">
                  <div className="lv-step-number">{step.number}</div>
                  <div className="lv-step-icon-wrap">
                    <Icon size={24} />
                  </div>
                  <h3 className="lv-step-title">{step.title}</h3>
                  <p className="lv-step-desc">{step.description}</p>
                  {i < steps.length - 1 && (
                    <div className="lv-step-connector" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── TESTIMONIALS ── */}
      <section id="testimonials" className="lv-section">
        <div className="lv-section-inner">
          <div className="lv-section-head">
            <div className="lv-section-badge">Testimonials</div>
            <h2 className="lv-section-h2">
              Trusted by agencies that
              <span className="lv-teal-text"> move fast</span>
            </h2>
          </div>

          <div className="lv-testimonials-grid">
            {testimonials.map((t) => (
              <div key={t.author} className="lv-testimonial-card">
                <div className="lv-stars">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} size={14} className="lv-star" />
                  ))}
                </div>
                <p className="lv-testimonial-quote">&quot;{t.quote}&quot;</p>
                <div className="lv-testimonial-author">
                  <div className="lv-testimonial-avatar">{t.avatar}</div>
                  <div>
                    <div className="lv-testimonial-name">{t.author}</div>
                    <div className="lv-testimonial-role">{t.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="pricing" className="lv-section lv-section-cloud">
        <div className="lv-section-inner">
          <div className="lv-section-head">
            <div className="lv-section-badge">Pricing</div>
            <h2 className="lv-section-h2">
              Simple, transparent
              <span className="lv-teal-text"> pricing</span>
            </h2>
            <p className="lv-section-sub">
              No hidden fees. Cancel any time.
            </p>
          </div>

          <div className="lv-pricing-grid">
            {pricingPlans.map((plan) => (
              <div
                key={plan.name}
                className={`lv-pricing-card ${plan.highlighted ? "lv-pricing-card-highlight" : ""}`}
              >
                {plan.highlighted && (
                  <div className="lv-pricing-popular">Most Popular</div>
                )}
                <div className="lv-pricing-name">{plan.name}</div>
                <div className="lv-pricing-price-row">
                  <span className="lv-pricing-price">{plan.price}</span>
                  <span className="lv-pricing-period">{plan.period}</span>
                </div>
                <p className="lv-pricing-desc">{plan.description}</p>
                <ul className="lv-pricing-features">
                  {plan.features.map((f) => (
                    <li key={f} className="lv-pricing-feature">
                      <Check size={15} className="lv-pricing-check" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href="/login"
                  className={plan.highlighted ? "lv-btn-primary lv-pricing-btn" : "lv-btn-outline-dark lv-pricing-btn"}
                >
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA BAND ── */}
      <section className="lv-cta-band">
        <div className="lv-cta-blob" />
        <div className="lv-cta-inner">
          <Shield size={40} className="lv-cta-icon" />
          <h2 className="lv-cta-h2">
            Ready to transform your
            <span className="lv-aqua-text"> content workflow?</span>
          </h2>
          <p className="lv-cta-sub">
            Join 500+ agencies already using LoomVerse AI to produce smarter
            content at scale.
          </p>
          <div className="lv-cta-actions">
            <Link href="/login" className="lv-btn-teal">
              Get Started Free
              <ChevronRight size={18} />
            </Link>
            <Link href="#features" className="lv-btn-ghost-light">
              Explore Features
            </Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="lv-footer">
        <div className="lv-footer-inner">
          <div className="lv-footer-brand">
            <Link href="/" className="lv-logo">
              <span className="lv-logo-icon">
                <Sparkles size={14} />
              </span>
              <span className="lv-logo-text">LoomVerse AI</span>
            </Link>
            <p className="lv-footer-tagline">
              Intelligent Marketing. Collaborative AI. Continuous Growth.
            </p>
          </div>

          <div className="lv-footer-links-group">
            <div className="lv-footer-col">
              <div className="lv-footer-col-title">Platform</div>
              {["Features", "Process", "Pricing", "Blog"].map((l) => (
                <a key={l} href={`#${l.toLowerCase()}`} className="lv-footer-link">{l}</a>
              ))}
            </div>
            <div className="lv-footer-col">
              <div className="lv-footer-col-title">Company</div>
              {["About", "Careers", "Contact", "Privacy"].map((l) => (
                <a key={l} href="#" className="lv-footer-link">{l}</a>
              ))}
            </div>
            <div className="lv-footer-col">
              <div className="lv-footer-col-title">Connect</div>
              {["Twitter / X", "LinkedIn", "GitHub", "Discord"].map((l) => (
                <a key={l} href="#" className="lv-footer-link">{l}</a>
              ))}
            </div>
          </div>
        </div>
        <div className="lv-footer-bottom">
          <span>© 2026 LoomVerse AI. All rights reserved.</span>
          <span>Built with ❤️ by the MMCS Team</span>
        </div>
      </footer>

      {/* ── PAGE-SCOPED STYLES ── */}
      <style>{`
        /* ── Reset / Base ── */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        .lv-page {
          min-height: 100vh;
          font-family: var(--font-inter, 'Inter', system-ui, sans-serif);
          background: #F7FAFC;
          color: #071A33;
          overflow-x: hidden;
        }

        /* ── NAV ── */
        .lv-nav {
          position: fixed; top: 0; left: 0; right: 0; z-index: 100;
          background: rgba(247,250,252,0.85);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border-bottom: 1px solid rgba(7,26,51,0.08);
        }
        .lv-nav-inner {
          max-width: 1200px; margin: 0 auto;
          display: flex; align-items: center; justify-content: space-between;
          padding: 0 28px; height: 68px;
        }
        .lv-logo {
          display: flex; align-items: center; gap: 8px;
          text-decoration: none; color: #071A33;
        }
        .lv-logo-icon {
          width: 30px; height: 30px; border-radius: 8px;
          background: #071A33;
          display: flex; align-items: center; justify-content: center;
          color: #48D7CE;
        }
        .lv-logo-text {
          font-size: 17px; font-weight: 700; letter-spacing: -0.3px;
          color: #071A33;
        }
        .lv-nav-links {
          display: flex; align-items: center; gap: 36px; list-style: none;
        }
        .lv-nav-link {
          font-size: 14px; color: #627083; text-decoration: none;
          transition: color 0.2s;
        }
        .lv-nav-link:hover { color: #071A33; }
        .lv-nav-actions { display: flex; align-items: center; gap: 12px; }
        .lv-btn-ghost {
          font-size: 14px; font-weight: 500; color: #071A33;
          text-decoration: none; padding: 8px 18px; border-radius: 8px;
          border: 1.5px solid rgba(7,26,51,0.15);
          transition: border-color 0.2s, background 0.2s;
        }
        .lv-btn-ghost:hover { border-color: #00A6A6; background: rgba(0,166,166,0.05); }
        .lv-btn-primary {
          font-size: 14px; font-weight: 600; color: #fff;
          text-decoration: none; padding: 9px 20px; border-radius: 8px;
          background: #00A6A6;
          transition: background 0.2s, box-shadow 0.2s;
        }
        .lv-btn-primary:hover { background: #007f7f; box-shadow: 0 4px 16px rgba(0,166,166,0.3); }

        /* ── HERO ── */
        .lv-hero {
          min-height: 100vh;
          padding: 120px 28px 80px;
          display: flex; align-items: center;
          gap: 60px;
          max-width: 1200px; margin: 0 auto;
          position: relative;
        }
        .lv-blob {
          position: fixed; border-radius: 50%; pointer-events: none;
          filter: blur(80px); opacity: 0.25;
        }
        .lv-blob-1 {
          width: 600px; height: 600px;
          top: -100px; left: -150px;
          background: radial-gradient(circle, #48D7CE 0%, #00A6A6 60%, transparent 100%);
        }
        .lv-blob-2 {
          width: 500px; height: 500px;
          top: 200px; right: -100px;
          background: radial-gradient(circle, #48D7CE 0%, transparent 70%);
        }
        .lv-blob-3 {
          width: 400px; height: 400px;
          bottom: 0; left: 30%;
          background: radial-gradient(circle, rgba(0,166,166,0.4) 0%, transparent 70%);
        }
        .lv-hero-content {
          flex: 1; min-width: 0; position: relative; z-index: 1;
        }
        .lv-badge {
          display: inline-flex; align-items: center; gap: 7px;
          padding: 6px 14px; border-radius: 100px;
          background: rgba(0,166,166,0.1); border: 1px solid rgba(0,166,166,0.25);
          font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
          color: #00A6A6; text-transform: uppercase; margin-bottom: 28px;
        }
        .lv-badge-icon { color: #00A6A6; }
        .lv-hero-h1 {
          font-size: clamp(38px, 5vw, 60px); font-weight: 800;
          line-height: 1.15; letter-spacing: -1.5px;
          color: #071A33; margin-bottom: 22px;
        }
        .lv-teal-text { color: #00A6A6; }
        .lv-aqua-text { color: #48D7CE; }
        .lv-hero-sub {
          font-size: 17px; color: #627083; line-height: 1.7;
          max-width: 520px; margin-bottom: 36px;
        }
        .lv-hero-ctas { display: flex; gap: 14px; flex-wrap: wrap; }
        .lv-btn-dark {
          display: inline-flex; align-items: center; justify-content: center;
          padding: 13px 28px; border-radius: 10px;
          background: #071A33; color: #fff;
          font-size: 15px; font-weight: 600; text-decoration: none;
          transition: background 0.2s, box-shadow 0.2s;
        }
        .lv-btn-dark:hover { background: #101827; box-shadow: 0 6px 20px rgba(7,26,51,0.25); }
        .lv-btn-outline {
          display: inline-flex; align-items: center; justify-content: center;
          padding: 13px 28px; border-radius: 10px;
          border: 1.5px solid rgba(7,26,51,0.2); color: #071A33;
          font-size: 15px; font-weight: 600; text-decoration: none;
          background: rgba(255,255,255,0.6);
          transition: border-color 0.2s, background 0.2s;
        }
        .lv-btn-outline:hover { border-color: #00A6A6; background: rgba(0,166,166,0.05); }

        /* Dashboard Preview */
        .lv-hero-preview {
          flex: 1; min-width: 0; position: relative; z-index: 1;
          display: flex; justify-content: center;
        }
        .lv-preview-card {
          width: 100%; max-width: 520px;
          background: rgba(255,255,255,0.9);
          border: 1px solid rgba(7,26,51,0.1);
          border-radius: 16px;
          box-shadow: 0 20px 60px rgba(7,26,51,0.12);
          overflow: hidden;
        }
        .lv-preview-header {
          display: flex; align-items: center; gap: 10px;
          padding: 12px 16px;
          background: #F7FAFC; border-bottom: 1px solid rgba(7,26,51,0.08);
        }
        .lv-preview-dots { display: flex; gap: 5px; }
        .lv-preview-dots span {
          width: 10px; height: 10px; border-radius: 50%;
          background: rgba(98,112,131,0.3);
        }
        .lv-preview-dots span:first-child { background: #ff5f57; }
        .lv-preview-dots span:nth-child(2) { background: #ffbd2e; }
        .lv-preview-dots span:last-child { background: #28ca41; }
        .lv-preview-url {
          font-size: 11px; color: #627083; font-family: monospace;
          padding: 3px 10px; background: rgba(98,112,131,0.1); border-radius: 4px;
        }
        .lv-preview-body { display: flex; height: 260px; }
        .lv-preview-sidebar {
          width: 130px; background: #071A33;
          padding: 16px 12px; display: flex; flex-direction: column; gap: 4px;
          flex-shrink: 0;
        }
        .lv-preview-sidebar-item {
          display: flex; align-items: center; gap: 8px;
          padding: 7px 10px; border-radius: 6px;
          font-size: 11px; color: rgba(255,255,255,0.6);
          transition: background 0.2s;
          cursor: default;
        }
        .lv-preview-sidebar-item:first-child {
          background: rgba(0,166,166,0.25); color: #48D7CE;
        }
        .lv-preview-dot {
          width: 6px; height: 6px; border-radius: 50%;
          background: rgba(255,255,255,0.3); flex-shrink: 0;
        }
        .lv-preview-sidebar-item:first-child .lv-preview-dot { background: #48D7CE; }
        .lv-preview-main {
          flex: 1; padding: 16px; display: flex; flex-direction: column; gap: 12px;
          overflow: hidden;
        }
        .lv-preview-stat-row { display: flex; gap: 10px; }
        .lv-preview-stat {
          flex: 1; background: #F7FAFC; border: 1px solid rgba(7,26,51,0.08);
          border-radius: 8px; padding: 10px; text-align: center;
        }
        .lv-preview-stat-val {
          display: block; font-size: 18px; font-weight: 700; color: #071A33;
        }
        .lv-preview-stat-label { font-size: 9px; color: #627083; }
        .lv-preview-chart {
          flex: 1; display: flex; align-items: flex-end; gap: 5px;
          background: #F7FAFC; border: 1px solid rgba(7,26,51,0.08);
          border-radius: 8px; padding: 10px;
        }
        .lv-preview-bar {
          flex: 1; background: linear-gradient(to top, #00A6A6, #48D7CE);
          border-radius: 3px 3px 0 0; min-height: 4px;
          transition: height 0.5s ease;
        }
        .lv-preview-feed {
          display: flex; flex-direction: column; gap: 5px;
        }
        .lv-preview-feed-item {
          display: flex; align-items: center; gap: 7px;
          font-size: 10px; color: #627083;
          padding: 5px 8px; background: #F7FAFC;
          border-radius: 5px; border: 1px solid rgba(7,26,51,0.06);
        }
        .lv-preview-feed-dot {
          width: 6px; height: 6px; border-radius: 50%;
          background: #00A6A6; flex-shrink: 0;
        }

        /* Floating badges */
        .lv-float-badge {
          position: absolute;
          display: flex; align-items: center; gap: 7px;
          padding: 8px 14px; border-radius: 100px;
          background: white; box-shadow: 0 4px 20px rgba(7,26,51,0.12);
          border: 1px solid rgba(7,26,51,0.08);
          font-size: 12px; font-weight: 600; color: #071A33;
          animation: float 4s ease-in-out infinite;
        }
        .lv-float-badge-1 { top: 60px; right: -20px; color: #00A6A6; animation-delay: 0s; }
        .lv-float-badge-2 { bottom: 80px; right: -10px; color: #071A33; animation-delay: 1.5s; }
        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-10px); }
        }

        /* ── STATS ── */
        .lv-stats-band {
          background: #071A33;
          display: flex; justify-content: center; gap: 0; flex-wrap: wrap;
        }
        .lv-stat-item {
          flex: 1; min-width: 180px;
          display: flex; flex-direction: column; align-items: center;
          padding: 40px 20px;
          border-right: 1px solid rgba(255,255,255,0.07);
        }
        .lv-stat-item:last-child { border-right: none; }
        .lv-stat-val {
          font-size: 42px; font-weight: 800; color: #48D7CE;
          letter-spacing: -1.5px; line-height: 1;
        }
        .lv-stat-label {
          font-size: 13px; color: rgba(255,255,255,0.5); margin-top: 8px;
        }

        /* ── SECTIONS ── */
        .lv-section { padding: 100px 28px; }
        .lv-section-navy {
          background: #101827;
        }
        .lv-section-cloud { background: #F0F5FA; }
        .lv-section-inner { max-width: 1200px; margin: 0 auto; }
        .lv-section-head {
          text-align: center; margin-bottom: 60px;
        }
        .lv-section-badge {
          display: inline-flex; padding: 5px 14px; border-radius: 100px;
          background: rgba(0,166,166,0.1); border: 1px solid rgba(0,166,166,0.25);
          font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
          color: #00A6A6; text-transform: uppercase; margin-bottom: 18px;
        }
        .lv-section-badge-light {
          background: rgba(72,215,206,0.15); border-color: rgba(72,215,206,0.3);
          color: #48D7CE;
        }
        .lv-section-h2 {
          font-size: clamp(28px, 3.5vw, 44px); font-weight: 800;
          color: #071A33; letter-spacing: -1px; line-height: 1.2;
          margin-bottom: 16px;
        }
        .lv-h2-light { color: #fff; }
        .lv-section-sub { font-size: 16px; color: #627083; max-width: 520px; margin: 0 auto; }
        .lv-sub-light { color: rgba(255,255,255,0.5); }

        /* ── FEATURES GRID ── */
        .lv-features-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
          gap: 24px;
        }
        .lv-feature-card {
          background: #fff; border: 1px solid rgba(7,26,51,0.08);
          border-radius: 16px; padding: 28px;
          position: relative; overflow: hidden;
          transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s;
          animation: fadeSlideUp 0.6s ease-out both;
        }
        .lv-feature-card:hover {
          transform: translateY(-6px);
          box-shadow: 0 16px 48px rgba(0,166,166,0.12);
          border-color: rgba(0,166,166,0.3);
        }
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(30px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .lv-feature-icon {
          width: 48px; height: 48px; border-radius: 12px;
          background: linear-gradient(135deg, rgba(0,166,166,0.15), rgba(72,215,206,0.15));
          display: flex; align-items: center; justify-content: center;
          color: #00A6A6; margin-bottom: 18px;
        }
        .lv-feature-title {
          font-size: 17px; font-weight: 700; color: #071A33; margin-bottom: 10px;
        }
        .lv-feature-desc { font-size: 14px; color: #627083; line-height: 1.65; }
        .lv-feature-arrow {
          position: absolute; bottom: 24px; right: 24px;
          width: 30px; height: 30px; border-radius: 50%;
          background: rgba(0,166,166,0.08);
          display: flex; align-items: center; justify-content: center;
          color: #00A6A6; opacity: 0; transition: opacity 0.3s;
        }
        .lv-feature-card:hover .lv-feature-arrow { opacity: 1; }

        /* ── STEPS ── */
        .lv-steps-grid {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
          gap: 32px; position: relative;
        }
        .lv-step-card {
          background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
          border-radius: 16px; padding: 32px 24px;
          position: relative;
        }
        .lv-step-number {
          font-size: 48px; font-weight: 900; letter-spacing: -2px;
          color: rgba(72,215,206,0.2); line-height: 1; margin-bottom: 16px;
        }
        .lv-step-icon-wrap {
          width: 48px; height: 48px; border-radius: 12px;
          background: rgba(0,166,166,0.2);
          display: flex; align-items: center; justify-content: center;
          color: #48D7CE; margin-bottom: 18px;
        }
        .lv-step-title {
          font-size: 17px; font-weight: 700; color: #fff; margin-bottom: 10px;
        }
        .lv-step-desc { font-size: 14px; color: rgba(255,255,255,0.45); line-height: 1.65; }
        .lv-step-connector {
          display: none;
        }

        /* ── TESTIMONIALS ── */
        .lv-testimonials-grid {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 24px;
        }
        .lv-testimonial-card {
          background: #fff; border: 1px solid rgba(7,26,51,0.08);
          border-radius: 16px; padding: 28px;
          transition: box-shadow 0.3s;
        }
        .lv-testimonial-card:hover {
          box-shadow: 0 12px 40px rgba(0,166,166,0.1);
        }
        .lv-stars { display: flex; gap: 3px; margin-bottom: 18px; }
        .lv-star { color: #00A6A6; fill: #00A6A6; }
        .lv-testimonial-quote {
          font-size: 15px; color: #071A33; line-height: 1.7; margin-bottom: 24px;
          font-style: italic;
        }
        .lv-testimonial-author { display: flex; align-items: center; gap: 12px; }
        .lv-testimonial-avatar {
          width: 40px; height: 40px; border-radius: 50%;
          background: linear-gradient(135deg, #00A6A6, #48D7CE);
          display: flex; align-items: center; justify-content: center;
          font-size: 13px; font-weight: 700; color: #fff; flex-shrink: 0;
        }
        .lv-testimonial-name { font-size: 14px; font-weight: 700; color: #071A33; }
        .lv-testimonial-role { font-size: 12px; color: #627083; }

        /* ── PRICING ── */
        .lv-pricing-grid {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
          gap: 24px; align-items: start;
        }
        .lv-pricing-card {
          background: #fff; border: 1px solid rgba(7,26,51,0.1);
          border-radius: 20px; padding: 36px 28px; position: relative;
        }
        .lv-pricing-card-highlight {
          background: #071A33; border-color: transparent;
          box-shadow: 0 20px 60px rgba(7,26,51,0.2);
          transform: scale(1.02);
        }
        .lv-pricing-popular {
          position: absolute; top: -14px; left: 50%; transform: translateX(-50%);
          background: linear-gradient(135deg, #00A6A6, #48D7CE);
          color: #071A33; font-size: 11px; font-weight: 700;
          padding: 4px 16px; border-radius: 100px; white-space: nowrap;
        }
        .lv-pricing-name {
          font-size: 14px; font-weight: 700; letter-spacing: 0.05em;
          text-transform: uppercase; color: #627083; margin-bottom: 12px;
        }
        .lv-pricing-card-highlight .lv-pricing-name { color: rgba(255,255,255,0.5); }
        .lv-pricing-price-row { display: flex; align-items: baseline; gap: 4px; margin-bottom: 10px; }
        .lv-pricing-price {
          font-size: 44px; font-weight: 800; letter-spacing: -2px; color: #071A33;
        }
        .lv-pricing-card-highlight .lv-pricing-price { color: #fff; }
        .lv-pricing-period { font-size: 15px; color: #627083; }
        .lv-pricing-card-highlight .lv-pricing-period { color: rgba(255,255,255,0.4); }
        .lv-pricing-desc {
          font-size: 14px; color: #627083; margin-bottom: 24px; line-height: 1.6;
        }
        .lv-pricing-card-highlight .lv-pricing-desc { color: rgba(255,255,255,0.45); }
        .lv-pricing-features { list-style: none; display: flex; flex-direction: column; gap: 10px; margin-bottom: 28px; }
        .lv-pricing-feature {
          display: flex; align-items: flex-start; gap: 10px;
          font-size: 14px; color: #071A33;
        }
        .lv-pricing-card-highlight .lv-pricing-feature { color: rgba(255,255,255,0.75); }
        .lv-pricing-check { color: #00A6A6; flex-shrink: 0; margin-top: 1px; }
        .lv-pricing-btn { display: block; text-align: center; width: 100%; }
        .lv-btn-outline-dark {
          display: inline-flex; align-items: center; justify-content: center;
          padding: 13px 24px; border-radius: 10px;
          border: 1.5px solid rgba(7,26,51,0.2); color: #071A33;
          font-size: 14px; font-weight: 600; text-decoration: none;
          transition: border-color 0.2s, background 0.2s;
        }
        .lv-btn-outline-dark:hover { border-color: #00A6A6; color: #00A6A6; }

        /* ── CTA BAND ── */
        .lv-cta-band {
          background: #071A33; position: relative; overflow: hidden;
          padding: 100px 28px; text-align: center;
        }
        .lv-cta-blob {
          position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
          width: 700px; height: 500px; border-radius: 50%;
          background: radial-gradient(ellipse, rgba(0,166,166,0.15) 0%, transparent 70%);
          pointer-events: none;
        }
        .lv-cta-inner { position: relative; max-width: 620px; margin: 0 auto; }
        .lv-cta-icon {
          color: #48D7CE; margin-bottom: 20px;
          animation: float 5s ease-in-out infinite;
        }
        .lv-cta-h2 {
          font-size: clamp(28px, 4vw, 44px); font-weight: 800;
          color: #fff; margin-bottom: 18px; line-height: 1.2;
        }
        .lv-cta-sub { font-size: 16px; color: rgba(255,255,255,0.5); margin-bottom: 36px; }
        .lv-cta-actions { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }
        .lv-btn-teal {
          display: inline-flex; align-items: center; gap: 7px;
          padding: 14px 28px; border-radius: 10px;
          background: linear-gradient(135deg, #00A6A6, #48D7CE);
          color: #071A33; font-size: 15px; font-weight: 700;
          text-decoration: none;
          transition: box-shadow 0.2s, opacity 0.2s;
        }
        .lv-btn-teal:hover { box-shadow: 0 8px 24px rgba(0,166,166,0.4); opacity: 0.92; }
        .lv-btn-ghost-light {
          display: inline-flex; align-items: center;
          padding: 14px 28px; border-radius: 10px;
          border: 1.5px solid rgba(255,255,255,0.2); color: rgba(255,255,255,0.7);
          font-size: 15px; font-weight: 600; text-decoration: none;
          transition: border-color 0.2s, color 0.2s;
        }
        .lv-btn-ghost-light:hover { border-color: #48D7CE; color: #48D7CE; }

        /* ── FOOTER ── */
        .lv-footer {
          background: #F7FAFC; border-top: 1px solid rgba(7,26,51,0.08);
          padding: 64px 28px 28px;
        }
        .lv-footer-inner {
          max-width: 1200px; margin: 0 auto;
          display: flex; gap: 60px; flex-wrap: wrap; margin-bottom: 48px;
        }
        .lv-footer-brand { flex: 1; min-width: 220px; }
        .lv-footer-tagline {
          font-size: 13px; color: #627083; margin-top: 14px; line-height: 1.6;
          max-width: 260px;
        }
        .lv-footer-links-group {
          display: flex; gap: 60px; flex-wrap: wrap;
        }
        .lv-footer-col { display: flex; flex-direction: column; gap: 10px; }
        .lv-footer-col-title {
          font-size: 12px; font-weight: 700; text-transform: uppercase;
          letter-spacing: 0.08em; color: #071A33; margin-bottom: 4px;
        }
        .lv-footer-link {
          font-size: 14px; color: #627083; text-decoration: none;
          transition: color 0.2s;
        }
        .lv-footer-link:hover { color: #00A6A6; }
        .lv-footer-bottom {
          max-width: 1200px; margin: 0 auto;
          display: flex; justify-content: space-between; align-items: center;
          flex-wrap: wrap; gap: 12px;
          padding-top: 24px; border-top: 1px solid rgba(7,26,51,0.08);
          font-size: 13px; color: #627083;
        }

        /* ── RESPONSIVE ── */
        @media (max-width: 900px) {
          .lv-hero { flex-direction: column; padding-top: 100px; }
          .lv-hero-preview { width: 100%; }
          .lv-float-badge { display: none; }
          .lv-nav-links { display: none; }
          .lv-stats-band { flex-wrap: wrap; }
          .lv-stat-item { min-width: 50%; border-right: none; border-bottom: 1px solid rgba(255,255,255,0.07); }
        }
        @media (max-width: 600px) {
          .lv-hero-h1 { font-size: 32px; }
          .lv-section-h2 { font-size: 26px; }
          .lv-features-grid, .lv-steps-grid, .lv-testimonials-grid, .lv-pricing-grid { grid-template-columns: 1fr; }
          .lv-pricing-card-highlight { transform: none; }
          .lv-footer-inner { flex-direction: column; }
          .lv-footer-links-group { gap: 32px; }
        }
      `}</style>
    </div>
  );
}
