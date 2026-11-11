/** @type {import('next').NextConfig} */
const api = process.env.NOTICE_API_URL || "http://localhost:8000";
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};
export default nextConfig;
