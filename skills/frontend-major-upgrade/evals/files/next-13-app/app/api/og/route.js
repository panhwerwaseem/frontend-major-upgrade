import { ImageResponse } from 'next/server';

export const runtime = 'experimental-edge';

export async function GET(request) {
  const title = new URL(request.url).searchParams.get('title') || 'Docs';
  return new ImageResponse(<div style={{ fontSize: 64 }}>{title}</div>, { width: 1200, height: 630 });
}
