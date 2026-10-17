declare module "@zumi/design-tokens/manifest" {
  const manifest: Record<string, Array<{ name: string; path: string; type: string; value: unknown; tier: "primitive" | "semantic"; description: string | null; ref: string | null }>>;
  export default manifest;
}
