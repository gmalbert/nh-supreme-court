/** Cloudflare Pages proxy to an Access-protected API behind a Tunnel. */
export async function onRequest({ request, env }) {
  const clientId = env.NHSC_ACCESS_CLIENT_ID;
  const clientSecret = env.NHSC_ACCESS_CLIENT_SECRET;
  let origin;
  try {
    origin = new URL(env.NHSC_API_ORIGIN);
    if (origin.protocol !== 'https:' || origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash) throw new Error('invalid origin');
  } catch {
    return new Response('API origin is not configured', { status: 503 });
  }
  if (!clientId || !clientSecret) return new Response('API access is not configured', { status: 503 });
  const incoming = new URL(request.url);
  if (!(incoming.pathname === '/api' || incoming.pathname.startsWith('/api/') || ['/docs', '/redoc', '/openapi.json'].includes(incoming.pathname))) {
    return new Response('Not found', { status: 404 });
  }
  const target = new URL(origin.origin);
  target.pathname = incoming.pathname;
  target.search = incoming.search;
  const headers = new Headers(request.headers);
  for (const name of ['host', 'cookie', 'authorization', 'cf-access-client-id', 'cf-access-client-secret', 'cf-access-jwt-assertion']) headers.delete(name);
  headers.set('CF-Access-Client-Id', clientId);
  headers.set('CF-Access-Client-Secret', clientSecret);
  try {
    const upstream = await fetch(new Request(target, new Request(request, { headers, redirect: 'manual' })));
    const outputHeaders = new Headers(upstream.headers);
    outputHeaders.delete('set-cookie');
    const location = outputHeaders.get('location');
    if (location) {
      const redirect = new URL(location, target);
      if (redirect.origin !== origin.origin) return new Response('API redirect rejected', { status: 502 });
      outputHeaders.set('location', `${redirect.pathname}${redirect.search}${redirect.hash}`);
    }
    return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: outputHeaders });
  } catch {
    return new Response('API service is unavailable', { status: 502 });
  }
}
