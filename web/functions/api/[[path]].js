/**
 * Cloudflare Pages Function — API 反向代理
 * 将前端 /api/* 请求转发到 HF Spaces 后端
 * 解决国内网络直接访问 HF Spaces 不稳定的问题
 *
 * 部署: 放在 web/functions/api/[[path]].js
 * 自动匹配路由: /api/* → 此函数
 */

export async function onRequest(context) {
  const { request, params, env } = context;

  // 从 Pages 环境变量读取， fallback 到明文兜底
  const BACKEND_URL = env.BACKEND_URL;

  // 构造后端真实 URL
  const url = new URL(request.url);
  const path = params.path ? params.path.join("/") : "";
  const backendUrl = `${BACKEND_URL}/api/${path}${url.search}`;

  // 转发请求头
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    // 不转发 hop-by-hop 头
    if (!["host", "connection", "content-length"].includes(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  // 覆盖 Host 为目标域名
  headers.set("Host", new URL(BACKEND_URL).host);

  try {
    const response = await fetch(backendUrl, {
      method: request.method,
      headers: headers,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      redirect: "follow",
    });

    // 构造响应
    const responseHeaders = new Headers();
    response.headers.forEach((value, key) => {
      if (!["content-security-policy", "x-frame-options", "strict-transport-security"].includes(key.toLowerCase())) {
        responseHeaders.set(key, value);
      }
    });
    // 允许跨域（Pages 部署后同源，这里设为通配）
    responseHeaders.set("Access-Control-Allow-Origin", "*");
    responseHeaders.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
    responseHeaders.set("Access-Control-Allow-Headers", "*");

    // 处理 OPTIONS 预检
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: responseHeaders,
      });
    }

    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: `代理失败: ${e.message}` }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
}
