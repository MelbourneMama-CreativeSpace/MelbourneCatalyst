"""Competitor Research agent — onboards a competitor's website (same
scrape + Claude-extraction pipeline as Company Analyzer, minus the
Knowledge Base embedding step) and generates a Company-vs-Competitor
comparison. Also offers Claude-suggested competitor *names* (not live
discovery — Claude can't browse to find or verify real URLs)."""
