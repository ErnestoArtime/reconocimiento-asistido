/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  typescript: {
    // El pass de typecheck de `next build` choca con un .d.ts interno de Next 16
    // (HeadersIterator) por skew con la lib TS; `skipLibCheck` no lo cubre en ese
    // paso. Nuestro codigo typecheckea limpio via `npm run typecheck` (tsc
    // --noEmit). Evitamos bloquear el build por un tipo interno de Next.
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
