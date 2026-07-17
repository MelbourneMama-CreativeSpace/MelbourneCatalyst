import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // A stray package-lock.json can exist in a parent directory (e.g. the
    // user's home directory) outside this repo. Without an explicit root,
    // Turbopack's lockfile-based root detection can walk up and pick that
    // directory instead of this project, which breaks all routing (every
    // page 404s because Turbopack is no longer looking inside `frontend/`).
    root: path.join(__dirname),
  },
};

export default nextConfig;
