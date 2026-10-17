import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@zumi/ui"],
  reactStrictMode: true,
};

export default nextConfig;
