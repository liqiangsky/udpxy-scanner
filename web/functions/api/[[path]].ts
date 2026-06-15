/**
 * Cloudflare Pages Functions — API 代理
 * 将 /api/* 请求转发到 HF Spaces 后端
 * 部署时需在 Pages 管理面板设置环境变量:
 *   API_BACKEND_URL = https://your-username-udpxy-scanner.hf.space
 */
export async function onRequest(context) {
  const { request, env } = context;
  const backend = env.API_BACKEND_URL || 'http://backend:7860';

  const url = new URL(request.url);
  const target = new URL(`${backend}${url.pathname}${url.search}`);

  return fetch(target.toString(), {
    method: request.method,
    headers: request.headers,
    body: request.body,
  });
}