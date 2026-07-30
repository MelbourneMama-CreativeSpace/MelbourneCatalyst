"""Intelligent chat agent — a tool-using Claude agent that answers a
signed-in user's questions by querying this app's own real data (companies,
trends, the knowledge base, content pipeline status). Unlike every other
agent in this codebase (a single forced-tool one-shot call), this is a
genuine multi-turn tool-use loop: Claude decides per-turn whether to call a
tool or just answer, over up to a bounded number of iterations."""
