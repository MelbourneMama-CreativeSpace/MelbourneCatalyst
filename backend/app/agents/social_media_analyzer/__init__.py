"""Platform Integration Agent — OAuth "connect your account" flows for
Instagram/Facebook, X/Twitter, LinkedIn, TikTok, and YouTube.

Scaffolded and gracefully "not configured" until a real app is
registered on each platform's developer console (see `.env.example`) —
same build-now-verify-later spirit as the Trend Analyzer's collectors.
Performance Tracking / Social Analytics / Channel Intelligence (the
other three Phase 6 sub-agents) are explicitly out of scope this round:
their DB schema exists (`PlatformMetricSnapshot`) but no metrics-fetching
logic does, since it can't be verified without a real connected account.
"""
