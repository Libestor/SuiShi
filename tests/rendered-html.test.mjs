import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the secure application shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>岁实 · 投资总览<\/title>/i);
  assert.match(html, /正在验证安全会话/);
  assert.doesNotMatch(html, /我的资产森林/);
  assert.doesNotMatch(html, /应急储备计算器/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("starter preview is removed and product management views are present", async () => {
  const [page, layout, dashboardClient, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/components/DashboardClient.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /DashboardClient/);
  assert.match(layout, /岁实 · 投资总览/);
  assert.match(dashboardClient, /平台设置/);
  assert.match(dashboardClient, /数据源与自动化/);
  assert.match(dashboardClient, /保存全部修改/);
  assert.match(dashboardClient, /逐月比较累计本金与当前金额/);
  assert.match(dashboardClient, /各篮子累计盈亏/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  await assert.rejects(access(new URL("../app/_sites-preview", import.meta.url)));
});
