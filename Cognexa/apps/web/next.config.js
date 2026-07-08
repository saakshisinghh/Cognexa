/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  experimental: {
    serverComponentsExternalPackages: [],
  },
  images: {
    domains: ["localhost"],
  },
  async redirects() {
    return [
      {
        // Roadmap doc calls this "Org Memory Engine executive dashboard"
        // at app/memory/ — we built it at app/knowledge/ instead (same
        // page, clearer name for what it actually shows). Redirect
        // rather than duplicate the page, so either URL works.
        source: "/memory",
        destination: "/knowledge",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://api:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;