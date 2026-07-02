/** @type {import('next').NextConfig} */

// The browser talks to this Next app; the app proxies /gw/* to the Donald
// gateway server-side, so the gateway can stay bound to 127.0.0.1 (never
// exposed to the internet) and there are no CORS headaches.
const GATEWAY_URL = process.env.GATEWAY_URL || "http://127.0.0.1:8765";

const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  async rewrites() {
    return [
      { source: "/gw/:path*", destination: `${GATEWAY_URL}/:path*` },
    ];
  },
};

module.exports = nextConfig;
