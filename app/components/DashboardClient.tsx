"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type View = "overview" | "assets" | "automation" | "achievements" | "settings";

type Basket = {
  id: string;
  code: "emergency" | "growth" | "risk";
  name: string;
  description: string;
  color: string;
  valueCny: number;
  ratio: number;
  targetRatio: number;
  cashBalanceCny: number;
  emergencyTargetCny: number | null;
  calculationNote?: string;
};

type Asset = {
  id: string;
  basketCode: Basket["code"];
  basketName: string;
  name: string;
  platform: string;
  symbol: string;
  currency: string;
  units: number;
  unitPrice: number;
  fxRate: number;
  valueCny: number;
  updatedAt: string;
  freshnessLabel: string;
  ageHours: number;
  source: string;
  sourceAttributes: Record<string, unknown>;
  note: string;
};

type Goal = {
  id: string;
  title: string;
  targetAmountCny: number;
  progress: number;
  remainingCny: number;
  rewardTitle: string;
  rewardDescription: string;
  targetDate: string | null;
  achievedAt: string | null;
};

type CurvePoint = { at: string; total: number; principal: number; profit: number };

type Dashboard = {
  asOf: string;
  totalAssetCny: number;
  principalCny: number;
  profitCny: number;
  profitRatio: number;
  baskets: Basket[];
  allocation: {
    mode: "dynamic" | "fixed";
    defaultContributionCny: number;
    growthRatio: number;
    riskRatio: number;
    targetGrowthRatio: number;
    targetRiskRatio: number;
  };
  assets: Asset[];
  curve: CurvePoint[];
  goals: Goal[];
};

type DataSourceView = {
  id: string;
  name: string;
  description: string;
  code: string;
  functionName: string;
  inputMapping: Record<string, string>;
  outputMapping: Record<string, string>;
  assetIds: string[];
  packages: string[];
  scheduleMinutes: number;
  enabled: boolean;
  lastRunAt: string | null;
  lastStatus: string;
  gitRevision: string;
};

type PlatformConfig = {
  allocationMode: "dynamic" | "fixed";
  growthRatio: number;
  riskRatio: number;
  defaultContributionCny: number;
  emergencyTargetCny: number;
  emergencyCalculationNote: string;
};

type NotificationRuleView = {
  id: string;
  name: string;
  eventType: string;
  metricPath: string;
  operator: ">" | ">=" | "<" | "<=" | "=";
  threshold: number | null;
  windowSeconds: number;
  maxDeliveries: number;
  enabled: boolean;
  webhookUrl: string;
  headersJson: Record<string, string>;
  bodyTemplate: string;
};

const now = new Date();
const DEMO: Dashboard = {
  asOf: now.toISOString(),
  totalAssetCny: 230644,
  principalCny: 212000,
  profitCny: 18644,
  profitRatio: 8.79,
  baskets: [
    {
      id: "emergency",
      code: "emergency",
      name: "应急储备金",
      description: "六个月必要支出，优先补足",
      color: "#718b6b",
      valueCny: 60000,
      ratio: 26.01,
      targetRatio: 0,
      cashBalanceCny: 12000,
      emergencyTargetCny: 60000,
    },
    {
      id: "growth",
      code: "growth",
      name: "成长性投资",
      description: "长期指数与基金投资",
      color: "#bf7b53",
      valueCny: 118873,
      ratio: 51.54,
      targetRatio: 80,
      cashBalanceCny: 6400,
      emergencyTargetCny: null,
    },
    {
      id: "risk",
      code: "risk",
      name: "高风险投资",
      description: "严格控制比例的高波动资产",
      color: "#8b6570",
      valueCny: 51771,
      ratio: 22.45,
      targetRatio: 20,
      cashBalanceCny: 2200,
      emergencyTargetCny: null,
    },
  ],
  allocation: {
    mode: "dynamic",
    defaultContributionCny: 12000,
    growthRatio: 69.66,
    riskRatio: 30.34,
    targetGrowthRatio: 80,
    targetRiskRatio: 20,
  },
  assets: [
    {
      id: "cash",
      basketCode: "emergency",
      basketName: "应急储备金",
      name: "银行现金管理",
      platform: "招商银行",
      symbol: "CASH-RESERVE",
      currency: "CNY",
      units: 1,
      unitPrice: 48000,
      fxRate: 1,
      valueCny: 48000,
      updatedAt: new Date(now.getTime() - 3 * 3600000).toISOString(),
      freshnessLabel: "3 小时前",
      ageHours: 3,
      source: "manual",
      sourceAttributes: {},
      note: "低波动、随时可取",
    },
    {
      id: "hs300",
      basketCode: "growth",
      basketName: "成长性投资",
      name: "沪深300指数基金",
      platform: "支付宝",
      symbol: "000300",
      currency: "CNY",
      units: 25630.1229,
      unitPrice: 2.5731,
      fxRate: 1,
      valueCny: 65949,
      updatedAt: new Date(now.getTime() - 8 * 3600000).toISOString(),
      freshnessLabel: "8 小时前",
      ageHours: 8,
      source: "data-source:基金净值",
      sourceAttributes: { fund_code: "000300" },
      note: "",
    },
    {
      id: "voo",
      basketCode: "growth",
      basketName: "成长性投资",
      name: "标普500指数基金",
      platform: "券商账户",
      symbol: "VOO",
      currency: "USD",
      units: 12.5,
      unitPrice: 518.42,
      fxRate: 7.18,
      valueCny: 46524,
      updatedAt: new Date(now.getTime() - 42 * 60000).toISOString(),
      freshnessLabel: "刚刚更新",
      ageHours: 0,
      source: "data-source:海外行情",
      sourceAttributes: { ticker: "VOO" },
      note: "",
    },
    {
      id: "btc",
      basketCode: "risk",
      basketName: "高风险投资",
      name: "比特币",
      platform: "数字资产账户",
      symbol: "BTCUSDT",
      currency: "USDT",
      units: 0.052,
      unitPrice: 93100,
      fxRate: 7.18,
      valueCny: 34759,
      updatedAt: new Date(now.getTime() - 12 * 60000).toISOString(),
      freshnessLabel: "刚刚更新",
      ageHours: 0,
      source: "data-source:数字资产行情",
      sourceAttributes: { pair: "BTCUSDT" },
      note: "",
    },
    {
      id: "chip",
      basketCode: "risk",
      basketName: "高风险投资",
      name: "半导体行业基金",
      platform: "天天基金",
      symbol: "CHIP-FUND",
      currency: "CNY",
      units: 8200,
      unitPrice: 1.924,
      fxRate: 1,
      valueCny: 15776,
      updatedAt: new Date(now.getTime() - 72 * 3600000).toISOString(),
      freshnessLabel: "3 天前",
      ageHours: 72,
      source: "manual",
      sourceAttributes: { fund_code: "009999" },
      note: "",
    },
  ],
  curve: [
    { at: "2026-02-10", total: 188000, principal: 188000, profit: 0 },
    { at: "2026-03-10", total: 192400, principal: 188000, profit: 4400 },
    { at: "2026-04-10", total: 199800, principal: 188000, profit: 11800 },
    { at: "2026-05-10", total: 207600, principal: 188000, profit: 19600 },
    { at: "2026-06-10", total: 218900, principal: 200000, profit: 18900 },
    { at: "2026-07-10", total: 226300, principal: 212000, profit: 14300 },
    { at: "2026-08-10", total: 230644, principal: 212000, profit: 18644 },
  ],
  goals: [
    {
      id: "goal-300k",
      title: "第一片真正的树荫",
      targetAmountCny: 300000,
      progress: 76.88,
      remainingCny: 69356,
      rewardTitle: "去山里住两晚",
      rewardDescription: "关掉工作消息，好好庆祝这段积累。",
      targetDate: "2027-04-07",
      achievedAt: null,
    },
  ],
};

function money(value: number, compact = false) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: compact ? 0 : 2,
  }).format(value);
}

function percent(value: number) {
  return `${value.toFixed(1)}%`;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("platform-unauthorized"));
    }
    const payload = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(payload.detail ?? `请求失败：${response.status}`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

function LoginView({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showToken, setShowToken] = useState(false);

  const login = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSubmitting(true); setMessage("");
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: form.get("token") }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: "登录失败" }));
        throw new Error(response.status === 429 ? "尝试次数过多，请稍后再试" : payload.detail === "Invalid credentials" ? "平台 Token 不正确" : payload.detail);
      }
      onAuthenticated();
    } catch (error) { setMessage(error instanceof Error ? error.message : "登录失败"); }
    finally { setSubmitting(false); }
  };

  return (
    <main className="login-page">
      <div className="login-atmosphere" aria-hidden="true"><i /><i /><i /></div>
      <section className="login-story">
        <div className="login-brand"><span>岁</span><div><strong>岁实</strong><small>投资总览</small></div></div>
        <div className="login-copy"><p className="section-kicker">私有资产花园</p><h1>让每一笔积累，<br />都在安静地生长。</h1><p>这里保存你的资产结构、投资节奏和每一个里程碑。输入平台 Token，继续查看今天长出了什么。</p></div>
        <div className="login-security-path"><span><i>1</i><strong>Nginx Basic Auth</strong><small>部署边界</small></span><b /> <span><i>2</i><strong>平台安全会话</strong><small>HttpOnly Cookie</small></span><b /> <span><i>3</i><strong>你的资产数据</strong><small>仅服务器端写入</small></span></div>
      </section>
      <section className="login-panel">
        <form className="login-card" onSubmit={login}>
          <div className="login-card-mark"><span>叶</span></div>
          <p className="section-kicker">身份验证</p>
          <h2>欢迎回来</h2>
          <p>平台会在服务器端验证凭证，不会将 Token 写入页面代码或浏览器存储。</p>
          <label>平台 Token<div className="token-input"><input name="token" type={showToken ? "text" : "password"} autoComplete="current-password" required placeholder="输入你的平台 Token" /><button type="button" onClick={() => setShowToken((current) => !current)}>{showToken ? "隐藏" : "显示"}</button></div></label>
          {message && <p className="login-error" role="alert">{message}</p>}
          <button className="login-submit" type="submit" disabled={submitting}>{submitting ? "正在验证…" : "进入我的资产森林"}<span>→</span></button>
          <div className="login-footnote"><span className="freshness-dot fresh" />会话默认保留 12 小时，退出后立即失效。</div>
        </form>
      </section>
    </main>
  );
}

export function DashboardClient() {
  const [authState, setAuthState] = useState<"checking" | "authenticated" | "anonymous">("checking");
  const [view, setView] = useState<View>("overview");
  const [data, setData] = useState<Dashboard>(DEMO);
  const [connection, setConnection] = useState<"loading" | "live" | "demo">("loading");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const dashboard = await api<Dashboard>("/dashboard");
      setData(dashboard);
      setConnection("live");
    } catch {
      setConnection("demo");
    }
  }, []);

  useEffect(() => {
    let active = true;
    fetch("/api/v1/auth/session", { credentials: "same-origin" })
      .then((response) => response.json())
      .then((session: { authenticated: boolean }) => { if (active) setAuthState(session.authenticated ? "authenticated" : "anonymous"); })
      .catch(() => { if (active) setAuthState("anonymous"); });
    const unauthorized = () => setAuthState("anonymous");
    window.addEventListener("platform-unauthorized", unauthorized);
    return () => { active = false; window.removeEventListener("platform-unauthorized", unauthorized); };
  }, []);

  useEffect(() => {
    if (authState !== "authenticated") return;
    let active = true;
    api<Dashboard>("/dashboard")
      .then((dashboard) => {
        if (!active) return;
        setData(dashboard);
        setConnection("live");
      })
      .catch(() => {
        if (active) setConnection("demo");
      });
    return () => { active = false; };
  }, [authState]);

  const snapshot = async () => {
    setNotice("正在更新估值快照…");
    try {
      await api("/snapshots", { method: "POST" });
      await refresh();
      setNotice("新的估值快照已经保存");
    } catch {
      setNotice("当前为预览数据；本地服务启动后即可保存快照");
    }
  };

  const logout = async () => {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => undefined);
    setAuthState("anonymous"); setData(DEMO); setView("overview");
  };

  if (authState === "checking") {
    return <main className="auth-loading"><span className="login-brand"><span>岁</span><span><strong>岁实</strong><small>正在验证安全会话…</small></span></span></main>;
  }
  if (authState === "anonymous") return <LoginView onAuthenticated={() => setAuthState("authenticated")} />;

  return (
    <div className="app-shell">
      <Sidebar view={view} setView={setView} />
      <div className="workspace">
        <Topbar connection={connection} onSnapshot={snapshot} onLogout={logout} />
        {notice && (
          <button className="toast" onClick={() => setNotice("")} aria-label="关闭提示">
            <span>{notice}</span><span>×</span>
          </button>
        )}
        <main>
          {view === "overview" && <Overview data={data} />}
          {view === "assets" && <AssetsView data={data} onChanged={refresh} />}
          {view === "automation" && <AutomationView assets={data.assets} />}
          {view === "achievements" && <AchievementsView data={data} />}
          {view === "settings" && <SettingsView data={data} onChanged={refresh} />}
        </main>
        <MobileNav view={view} setView={setView} />
      </div>
    </div>
  );
}

function Sidebar({ view, setView }: { view: View; setView: (view: View) => void }) {
  const items: { id: View; label: string; glyph: string }[] = [
    { id: "overview", label: "总览", glyph: "田" },
    { id: "assets", label: "资产", glyph: "叶" },
    { id: "automation", label: "自动化", glyph: "流" },
    { id: "achievements", label: "成就", glyph: "果" },
    { id: "settings", label: "设置", glyph: "设" },
  ];
  return (
    <aside className="sidebar">
      <button className="brand" onClick={() => setView("overview")}>
        <span className="brand-mark">岁</span>
        <span><strong>岁实</strong><small>投资总览</small></span>
      </button>
      <nav aria-label="主要导航">
        {items.map((item) => (
          <button
            key={item.id}
            className={view === item.id ? "nav-item active" : "nav-item"}
            onClick={() => setView(item.id)}
          >
            <span className="nav-glyph">{item.glyph}</span>{item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-quote">
        <span className="tiny-leaf" />
        <p>每一笔克制的积累，<br />都会长成选择的底气。</p>
      </div>
    </aside>
  );
}

function MobileNav({ view, setView }: { view: View; setView: (view: View) => void }) {
  return (
    <nav className="mobile-nav" aria-label="手机导航">
      {(["overview", "assets", "automation", "achievements", "settings"] as View[]).map((id) => (
        <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id)}>
          {id === "overview" ? "总览" : id === "assets" ? "资产" : id === "automation" ? "自动化" : id === "achievements" ? "成就" : "设置"}
        </button>
      ))}
    </nav>
  );
}

function Topbar({ connection, onSnapshot, onLogout }: { connection: string; onSnapshot: () => void; onLogout: () => void }) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">2026 · 盛夏</p>
        <p className="greeting">晚上好，看看今天长出了什么。</p>
      </div>
      <div className="topbar-actions">
        <span className={`connection ${connection}`}>
          <i />{connection === "live" ? "数据已连接" : connection === "demo" ? "预览数据" : "正在连接"}
        </span>
        <button className="logout-button" onClick={onLogout}>退出</button>
        <button className="primary-button" onClick={onSnapshot}>更新估值</button>
      </div>
    </header>
  );
}

function Overview({ data }: { data: Dashboard }) {
  const goal = data.goals.find((item) => !item.achievedAt) ?? data.goals[0];
  const staleAssets = data.assets.filter((asset) => asset.ageHours >= 24);
  return (
    <div className="page-stack">
      <section className="hero">
        <div className="hero-copy">
          <p className="section-kicker">我的资产森林</p>
          <h1>{money(data.totalAssetCny, true)}</h1>
          <div className="hero-deltas">
            <span className="positive">累计盈亏 +{money(data.profitCny, true)}</span>
            <span>本金 {money(data.principalCny, true)}</span>
            <span>更新于刚刚</span>
          </div>
        </div>
        {goal && <GoalProgress goal={goal} />}
      </section>

      <section className="panel hierarchy-panel">
        <PanelHeading title="资产结构树" subtitle="总资产 → 三个篮子 → 具体产品" action={`${data.assets.length} 项产品 · 点击篮子收起`} />
        <AssetTree total={data.totalAssetCny} baskets={data.baskets} assets={data.assets} />
      </section>

      <section className="overview-grid lower">
        <div className="panel chart-panel">
          <PanelHeading title="生长曲线" subtitle="本金与市场共同托举资产" action="近 6 个月" />
          <GrowthChart curve={data.curve} />
        </div>
        <div className="panel allocation-panel">
          <PanelHeading title="配置罗盘" subtitle="成长与高风险篮子" action="动态平衡" />
          <AllocationCompass data={data} />
        </div>
      </section>

      <section className="panel freshness-panel full-width">
        <PanelHeading title="数据状态" subtitle="最后一次已知数据始终参与计算" action={`${staleAssets.length} 项待关注`} />
        <div className="freshness-list">
            {data.assets.slice(0, 5).map((asset) => (
              <div className="freshness-row" key={asset.id}>
                <span className={`freshness-dot ${asset.ageHours >= 48 ? "stale" : asset.ageHours >= 24 ? "aging" : "fresh"}`} />
                <div><strong>{asset.name}</strong><small>{asset.source.replace("data-source:", "自动 · ")}</small></div>
                <time>{asset.freshnessLabel}</time>
              </div>
            ))}
        </div>
      </section>
    </div>
  );
}

function PanelHeading({ title, subtitle, action }: { title: string; subtitle: string; action: string }) {
  return (
    <header className="panel-heading">
      <div><h2>{title}</h2><p>{subtitle}</p></div>
      <span>{action}</span>
    </header>
  );
}

function GoalProgress({ goal }: { goal: Goal }) {
  const progress = Math.min(100, goal.progress);
  return (
    <div className="goal-card">
      <div className="goal-ring" style={{ "--progress": `${progress * 3.6}deg` } as React.CSSProperties}>
        <span><strong>{Math.round(progress)}%</strong><small>已完成</small></span>
      </div>
      <div className="goal-copy">
        <p>当前里程碑</p>
        <h2>{goal.title}</h2>
        <span>还差 {money(goal.remainingCny, true)} · 目标 {money(goal.targetAmountCny, true)}</span>
      </div>
      <div className="goal-reward"><small>达成奖励</small><strong>{goal.rewardTitle || "给自己一个拥抱"}</strong></div>
    </div>
  );
}

function AssetTree({ total, baskets, assets }: { total: number; baskets: Basket[]; assets: Asset[] }) {
  const [expanded, setExpanded] = useState<Set<Basket["code"]>>(
    () => new Set(["emergency", "growth", "risk"]),
  );
  const toggle = (code: Basket["code"]) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };
  return (
    <div className="asset-hierarchy" aria-label="资产结构树">
      <div className="asset-root-row">
        <div className="asset-root-node">
          <span className="root-orbit"><i /></span>
          <span className="root-copy"><small>ROOT · 总资产</small><strong>{money(total, true)}</strong></span>
          <span className="root-ratio"><b>100%</b><small>全部资产</small></span>
        </div>
      </div>
      <div className="basket-branches">
        {baskets.map((basket) => {
          const products = assets.filter((asset) => asset.basketCode === basket.code);
          const isExpanded = expanded.has(basket.code);
          const glyph = basket.code === "emergency" ? "安" : basket.code === "growth" ? "长" : "险";
          const entries = [
            ...products.map((asset) => ({
              id: asset.id,
              name: asset.name,
              meta: `${asset.platform || "未设置平台"} · ${asset.freshnessLabel}`,
              value: asset.valueCny,
              kind: "product",
            })),
            ...(basket.cashBalanceCny > 0 ? [{
              id: `${basket.id}-cash`, name: "待购买现金", meta: "已归属篮子 · 暂未投入产品",
              value: basket.cashBalanceCny, kind: "cash",
            }] : []),
          ];
          return (
            <div className={`basket-column ${basket.code}`} key={basket.id}>
              <button className="basket-node" type="button" aria-expanded={isExpanded} onClick={() => toggle(basket.code)}>
                <span className="basket-glyph">{glyph}</span>
                <span className="basket-node-copy"><small>{basket.description}</small><strong>{basket.name}</strong><b>{money(basket.valueCny, true)}</b></span>
                <span className="basket-node-ratio"><strong>{percent(basket.ratio)}</strong><small>占总资产</small><i className={isExpanded ? "expanded" : ""}>⌄</i></span>
              </button>
              {isExpanded && (
                <div className="product-branches">
                  {entries.map((entry) => (
                    <div className={`product-node ${entry.kind}`} key={entry.id}>
                      <span className="product-mark">{entry.kind === "cash" ? "现" : entry.name.slice(0, 1)}</span>
                      <span className="product-copy"><strong>{entry.name}</strong><small>{entry.meta}</small></span>
                      <span className="product-value"><strong>{money(entry.value, true)}</strong><small>{percent(basket.valueCny ? entry.value / basket.valueCny * 100 : 0)} 篮内</small></span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AllocationCompass({ data }: { data: Dashboard }) {
  const [amount, setAmount] = useState(() => String(data.allocation.defaultContributionCny));
  const [mode, setMode] = useState<"dynamic" | "fixed">(() => data.allocation.mode);
  const [preview, setPreview] = useState<{ emergency_cny: string; growth_cny: string; risk_cny: string } | null>(null);
  const allocate = async () => {
    try {
      const result = await api<typeof preview>("/allocations/preview", {
        method: "POST",
        body: JSON.stringify({
          contribution_cny: amount,
          mode,
          growth_ratio: String(data.allocation.targetGrowthRatio / 100),
          risk_ratio: String(data.allocation.targetRiskRatio / 100),
        }),
      });
      setPreview(result);
    } catch {
      const value = Number(amount) || 0;
      setPreview({ emergency_cny: "0", growth_cny: String(value), risk_cny: "0" });
    }
  };
  const growth = data.allocation.growthRatio;
  const risk = data.allocation.riskRatio;
  return (
    <div className="compass-stack">
      <div className="ratio-summary">
        <div><small>成长</small><strong>{percent(growth)}</strong><span>目标 {percent(data.allocation.targetGrowthRatio)}</span></div>
        <div className="ratio-track"><i style={{ width: `${growth}%` }} /><b style={{ left: `${data.allocation.targetGrowthRatio}%` }} /></div>
        <div className="risk-number"><small>高风险</small><strong>{percent(risk)}</strong><span>偏高 {percent(Math.max(0, risk - data.allocation.targetRiskRatio))}</span></div>
      </div>
      <div className="allocation-advice">
        <span className="advice-mark">↘</span>
        <div><strong>下一笔优先进入成长篮子</strong><p>无需卖出，使用新增资金逐步回到 80 / 20。</p></div>
      </div>
      <div className="allocation-form">
        <label>计划投入<input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" /></label>
        <div className="mode-toggle">
          <button className={mode === "dynamic" ? "active" : ""} onClick={() => setMode("dynamic")}>动态</button>
          <button className={mode === "fixed" ? "active" : ""} onClick={() => setMode("fixed")}>固定</button>
        </div>
        <button className="text-button" onClick={allocate}>试算</button>
      </div>
      {preview && (
        <div className="allocation-result">
          <span>应急 <b>{money(Number(preview.emergency_cny), true)}</b></span>
          <span>成长 <b>{money(Number(preview.growth_cny), true)}</b></span>
          <span>高风险 <b>{money(Number(preview.risk_cny), true)}</b></span>
        </div>
      )}
    </div>
  );
}

function GrowthChart({ curve }: { curve: CurvePoint[] }) {
  const values = curve.length ? curve : DEMO.curve;
  const min = Math.min(...values.map((point) => point.principal)) * 0.96;
  const max = Math.max(...values.map((point) => point.total)) * 1.02;
  const range = Math.max(1, max - min);
  const polygon = (key: "total" | "principal") => {
    const points = values.map((point, index) => {
      const x = values.length === 1 ? 50 : (index / (values.length - 1)) * 100;
      const y = 100 - ((point[key] - min) / range) * 100;
      return `${x}% ${y}%`;
    });
    return `polygon(0% 100%, ${points.join(", ")}, 100% 100%)`;
  };
  return (
    <div className="growth-chart">
      <div className="chart-legend"><span><i className="total" />总资产</span><span><i className="principal" />累计本金</span></div>
      <div className="chart-canvas">
        <div className="chart-grid-lines"><i /><i /><i /><i /></div>
        <div className="chart-shape principal" style={{ clipPath: polygon("principal") }} />
        <div className="chart-shape total" style={{ clipPath: polygon("total") }} />
        <div className="chart-end-value"><small>现在</small><strong>{money(values.at(-1)?.total ?? 0, true)}</strong></div>
      </div>
      <div className="chart-axis"><span>2月</span><span>4月</span><span>6月</span><span>现在</span></div>
    </div>
  );
}

function AssetsView({ data, onChanged }: { data: Dashboard; onChanged: () => Promise<void> }) {
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState<Asset | null>(null);
  const [message, setMessage] = useState("");
  const total = data.assets.reduce((sum, asset) => sum + asset.valueCny, 0);

  const createAsset = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const sourceAttributes = JSON.parse(String(form.get("sourceAttributes") || "{}"));
      await api("/assets", {
        method: "POST",
        body: JSON.stringify({
          basket_code: form.get("basket"), name: form.get("name"), platform: form.get("platform"),
          symbol: form.get("symbol"), currency: form.get("currency"), units: form.get("units"),
          unit_price: form.get("price"), fx_rate: form.get("fxRate"), source_attributes: sourceAttributes,
          note: form.get("note"),
        }),
      });
      setShowForm(false);
      setMessage("资产已添加");
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "添加失败");
    }
  };

  const updateAsset = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    try {
      const sourceAttributes = JSON.parse(String(form.get("sourceAttributes") || "{}"));
      await api(`/assets/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          basket_code: form.get("basket"), name: form.get("name"), platform: form.get("platform"),
          symbol: form.get("symbol"), currency: form.get("currency"), units: form.get("units"),
          unit_price: form.get("price"), fx_rate: form.get("fxRate"), source_attributes: sourceAttributes,
          note: form.get("note"),
        }),
      });
      setSelected(null); setMessage("资产资料与最新估值已更新，变动已写入历史"); await onChanged();
    } catch (error) { setMessage(error instanceof Error ? error.message : "更新失败"); }
  };

  const deleteAsset = async () => {
    if (!selected) return;
    if (!window.confirm(`确定删除“${selected.name}”吗？该资产会从当前台账中移除，历史估值将保留。`)) return;
    try {
      await api(`/assets/${selected.id}`, { method: "DELETE" });
      setSelected(null);
      setMessage(`已删除“${selected.name}”，历史记录已保留`);
      await onChanged();
    } catch (error) { setMessage(error instanceof Error ? error.message : "删除失败"); }
  };

  return (
    <div className="page-stack subpage">
      <section className="subpage-title"><div><p className="section-kicker">资产台账</p><h1>每一片叶子，都有来处。</h1><p>共 {data.assets.length} 项资产，产品价值 {money(total, true)}。</p></div><button className="primary-button" onClick={() => setShowForm(!showForm)}>＋ 添加资产</button></section>
      {message && <p className="inline-message">{message}</p>}
      {showForm && (
        <form className="panel asset-form" onSubmit={createAsset}>
          <label>资产名称<input name="name" required placeholder="例如：沪深300指数基金" /></label>
          <label>所属篮子<select name="basket"><option value="growth">成长性投资</option><option value="risk">高风险投资</option><option value="emergency">应急储备金</option></select></label>
          <label>平台<input name="platform" placeholder="支付宝 / 券商" /></label>
          <label>资产代码<input name="symbol" placeholder="000300" /></label>
          <label>币种<select name="currency"><option>CNY</option><option>USD</option><option>HKD</option><option>USDT</option></select></label>
          <label>份额<input name="units" required type="number" step="any" min="0" /></label>
          <label>单价<input name="price" required type="number" step="any" min="0" /></label>
          <label>人民币汇率<input name="fxRate" required type="number" step="any" min="0.000001" defaultValue="1" /></label>
          <label className="wide-field">数据源属性（JSON）<textarea name="sourceAttributes" defaultValue="{}" placeholder={'{"fund_code":"000300"}'} /></label>
          <label className="wide-field">备注<textarea name="note" placeholder="记录持有理由、计算口径等" /></label>
          <div className="form-actions"><button type="button" onClick={() => setShowForm(false)}>取消</button><button className="primary-button" type="submit">保存资产</button></div>
        </form>
      )}
      <section className="panel asset-table-panel">
        <div className="asset-table-head"><span>资产 / 平台</span><span>所属篮子</span><span>份额 × 单价</span><span>人民币价值</span><span>数据状态</span><span /></div>
        {data.assets.map((asset) => (
          <div className="asset-row" key={asset.id}>
            <div className="asset-name"><span className={`asset-icon ${asset.basketCode}`}>{asset.name.slice(0, 1)}</span><span><strong>{asset.name}</strong><small>{asset.platform} · {asset.symbol}</small></span></div>
            <span className={`basket-pill ${asset.basketCode}`}>{asset.basketName}</span>
            <span>{asset.units.toLocaleString("zh-CN", { maximumFractionDigits: 4 })} × {asset.unitPrice.toLocaleString("zh-CN") } {asset.currency}</span>
            <strong>{money(asset.valueCny, true)}</strong>
            <span className={asset.ageHours >= 48 ? "status-stale" : "status-fresh"}>{asset.freshnessLabel}</span>
            <button className="row-action" onClick={() => setSelected(asset)}>编辑</button>
          </div>
        ))}
      </section>
      {selected && (
        <div className="modal-backdrop">
          <button className="modal-dismiss" type="button" aria-label="关闭资产编辑窗口" onClick={() => setSelected(null)} />
          <form className="modal-card asset-edit-modal" role="dialog" aria-modal="true" aria-labelledby="asset-edit-title" onSubmit={updateAsset}>
            <div className="modal-heading"><div><p className="section-kicker">人工维护</p><h2 id="asset-edit-title">编辑 {selected.name}</h2></div><span>修改份额、单价或汇率会形成新的估值记录</span></div>
            <div className="asset-edit-grid">
              <label>资产名称<input name="name" required defaultValue={selected.name} /></label>
              <label>所属篮子<select name="basket" defaultValue={selected.basketCode}><option value="emergency">应急储备金</option><option value="growth">成长性投资</option><option value="risk">高风险投资</option></select></label>
              <label>所属平台<input name="platform" defaultValue={selected.platform} /></label>
              <label>资产代码<input name="symbol" defaultValue={selected.symbol} /></label>
              <label>币种<select name="currency" defaultValue={selected.currency}><option>CNY</option><option>USD</option><option>HKD</option><option>USDT</option></select></label>
              <label>持有份额<input name="units" required type="number" step="any" min="0" defaultValue={selected.units} /></label>
              <label>当前单价<input name="price" required type="number" step="any" min="0" defaultValue={selected.unitPrice} /></label>
              <label>人民币汇率<input name="fxRate" required type="number" step="any" min="0.000001" defaultValue={selected.fxRate} /></label>
              <label className="wide-field">数据源属性（JSON）<textarea name="sourceAttributes" defaultValue={JSON.stringify(selected.sourceAttributes, null, 2)} placeholder={'{"fund_code":"000300"}'} /></label>
              <label className="wide-field">备注<textarea name="note" defaultValue={selected.note} placeholder="记录持有理由、计算口径等" /></label>
            </div>
            <div className="form-actions"><button type="button" className="danger-button" onClick={deleteAsset}>删除资产</button><span /><button type="button" onClick={() => setSelected(null)}>取消</button><button className="primary-button" type="submit">保存全部修改</button></div>
          </form>
        </div>
      )}
    </div>
  );
}

function freshDataSource(): DataSourceView {
  return {
    id: "",
    name: "基金净值",
    description: "批量获取基金单价，可继续绑定新增的基金资产。",
    code: `def fetch(payload):\n    results = []\n    for item in payload.get("items", []):\n        results.append({\n            "asset_id": item["asset_id"],\n            "price": item.get("fallback_price", 0),\n        })\n    return {"items": results}\n`,
    functionName: "fetch",
    inputMapping: { fund_code: "source_attributes.fund_code", fallback_price: "unit_price" },
    outputMapping: { unit_price: "price" },
    assetIds: [], packages: ["httpx"], scheduleMinutes: 1440, enabled: false,
    lastRunAt: null, lastStatus: "", gitRevision: "",
  };
}

const INPUT_FIELD_REFERENCE = [
  { value: "name", title: "资产名称", description: "用于脚本日志或按名称区分资产，例如“沪深300指数基金”。" },
  { value: "platform", title: "持有平台", description: "资产所在的平台或券商，例如支付宝、券商账户。" },
  { value: "symbol", title: "资产代码", description: "查询市场行情时使用的代码，例如 000300、VOO。" },
  { value: "unit_price", title: "当前单价", description: "上一次记录的单价；可作为脚本查询失败时的备用值。" },
  { value: "fx_rate", title: "人民币汇率", description: "外币资产换算成人民币时使用的汇率。" },
  { value: "units", title: "持有数量", description: "当前持有的份额或币数。" },
  { value: "currency", title: "计价币种", description: "资产单价的币种，例如 CNY、USD、USDT。" },
  { value: "source_attributes.字段名", title: "自定义资料", description: "资产里额外保存的资料，例如 source_attributes.fund_code。" },
];

const OUTPUT_FIELD_REFERENCE = [
  { value: "unit_price", title: "当前单价", description: "将脚本返回的价格写回资产，并记录一笔新估值。" },
  { value: "fx_rate", title: "人民币汇率", description: "将脚本返回的汇率写回资产。" },
  { value: "source_attributes.字段名", title: "自定义资料", description: "保存脚本返回的附加信息，例如净值日期。" },
];

function MappingEditor({
  title, value, onChange, output = false,
}: {
  title: string;
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  output?: boolean;
}) {
  const entries = Object.entries(value);
  const update = (index: number, side: 0 | 1, next: string) => {
    const changed = entries.map(([left, right]) => [left, right] as [string, string]);
    changed[index][side] = next;
    onChange(Object.fromEntries(changed));
  };
  const remove = (index: number) => onChange(Object.fromEntries(entries.filter((_, row) => row !== index)));
  const add = () => {
    let key = output ? "unit_price" : "function_field";
    let suffix = 2;
    while (key in value) key = `${output ? "unit_price" : "function_field"}_${suffix++}`;
    onChange({ ...value, [key]: output ? "result_field" : "asset_field" });
  };
  const assetFieldListId = output ? "writable-asset-fields" : "readable-asset-fields";
  return (
    <div className="mapping-editor">
      <div className="mapping-title"><div><strong>{title}</strong></div><button type="button" onClick={add}>＋ 添加字段</button></div>
      <div className="mapping-columns"><span>{output ? "要更新的资产资料" : "脚本中读取的名称"}</span><span>{output ? "脚本返回的名称" : "每项资产提供的资料"}</span></div>
      {entries.length === 0 && <p className="empty-copy">尚未添加字段。</p>}
      {entries.map(([left, right], index) => (
        <div className="mapping-edit-row" key={`${left}-${index}`}>
          <input aria-label={output ? "写回资产的字段" : "脚本接收的变量名"} list={output ? assetFieldListId : undefined} value={left} onChange={(event) => update(index, 0, event.target.value)} />
          <span>→</span>
          <input aria-label={output ? "脚本返回的字段" : "从资产读取的字段"} list={output ? undefined : assetFieldListId} value={right} onChange={(event) => update(index, 1, event.target.value)} />
          <button type="button" aria-label="移除映射" onClick={() => remove(index)}>×</button>
        </div>
      ))}
      <datalist id="readable-asset-fields"><option value="name" /><option value="platform" /><option value="symbol" /><option value="unit_price" /><option value="fx_rate" /><option value="units" /><option value="currency" /><option value="source_attributes.fund_code" /></datalist>
      <datalist id="writable-asset-fields"><option value="unit_price" /><option value="fx_rate" /><option value="source_attributes.net_value_date" /></datalist>
    </div>
  );
}

function FieldGuide({ selectedCount, onClose }: { selectedCount: number; onClose: () => void }) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="field-guide-title">
      <button className="modal-dismiss" type="button" aria-label="关闭字段说明" onClick={onClose} />
      <section className="modal-card field-guide-modal">
        <div className="modal-heading"><div><p className="section-kicker">字段说明</p><h2 id="field-guide-title">脚本如何处理资产</h2></div><button type="button" className="row-action" onClick={onClose}>关闭</button></div>
        <div className="field-guide-flow"><div><b>1</b><span>脚本运行 1 次</span></div><i>→</i><div><b>2</b><span>收到 {selectedCount || "所选"} 条资产记录</span></div><i>→</i><div><b>3</b><span>按 asset_id 写回结果</span></div></div>
        <p className="field-guide-copy">每选择一项资产，系统就在 <code>payload.items</code> 中加入一条记录。Python 代码循环处理这些记录，并为每项资产返回一条带 <code>asset_id</code> 的结果。</p>
        <h3>可提供给脚本的资料</h3>
        <div className="field-reference">{INPUT_FIELD_REFERENCE.map((field) => <div key={field.value}><code>{field.value}</code><strong>{field.title}</strong><span>{field.description}</span></div>)}</div>
        <h3>允许脚本更新的资料</h3>
        <div className="field-reference">{OUTPUT_FIELD_REFERENCE.map((field) => <div key={field.value}><code>{field.value}</code><strong>{field.title}</strong><span>{field.description}</span></div>)}</div>
      </section>
    </div>
  );
}

function AutomationView({ assets }: { assets: Asset[] }) {
  const [sources, setSources] = useState<DataSourceView[]>([]);
  const [draft, setDraft] = useState<DataSourceView>(freshDataSource);
  const [status, setStatus] = useState("正在读取脚本库…");
  const [showFieldGuide, setShowFieldGuide] = useState(false);
  const selectedAssets = assets.filter((asset) => draft.assetIds.includes(asset.id));

  useEffect(() => {
    let active = true;
    api<DataSourceView[]>("/data-sources")
      .then((rows) => {
        if (!active) return;
        setSources(rows);
        if (rows[0]) setDraft(rows[0]);
        setStatus(rows.length ? "" : "还没有数据源，可以从第一个基金脚本开始。");
      })
      .catch((error) => { if (active) setStatus(error instanceof Error ? error.message : "数据源读取失败"); });
    return () => { active = false; };
  }, []);

  const reload = async (selectedId?: string) => {
    const rows = await api<DataSourceView[]>("/data-sources");
    setSources(rows);
    const current = rows.find((row) => row.id === selectedId) ?? rows[0];
    setDraft(current ?? freshDataSource());
  };

  const changeDraft = <K extends keyof DataSourceView>(key: K, value: DataSourceView[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const saveSource = async () => {
    try {
      const inputMapping = Object.fromEntries(Object.entries(draft.inputMapping).filter(([key, value]) => key.trim() && value.trim()));
      const outputMapping = Object.fromEntries(Object.entries(draft.outputMapping).filter(([key, value]) => key.trim() && value.trim()));
      const payload = {
        name: draft.name, description: draft.description, code: draft.code, function_name: draft.functionName,
        input_mapping: inputMapping, output_mapping: outputMapping, asset_ids: draft.assetIds,
        packages: draft.packages, schedule_minutes: draft.scheduleMinutes, enabled: draft.enabled,
      };
      const response = await api<{ id: string; gitRevision: string }>(draft.id ? `/data-sources/${draft.id}` : "/data-sources", {
        method: draft.id ? "PATCH" : "POST", body: JSON.stringify(payload),
      });
      await reload(response.id);
      setStatus(`已保存，Git 版本 ${response.gitRevision.slice(0, 8)}`);
    } catch (error) { setStatus(error instanceof Error ? error.message : "保存失败"); }
  };

  const runSource = async () => {
    if (!draft.id) { setStatus("请先保存脚本再执行。"); return; }
    try {
      setStatus("正在执行脚本…");
      const result = await api<{ status: string; durationMs: number }>(`/data-sources/${draft.id}/execute`, {
        method: "POST", body: JSON.stringify({ asset_ids: [] }),
      });
      await reload(draft.id);
      setStatus(`执行${result.status === "success" ? "成功" : "完成"}，用时 ${result.durationMs} ms`);
    } catch (error) { setStatus(error instanceof Error ? error.message : "执行失败"); }
  };

  const deleteSource = async () => {
    if (!draft.id) return;
    if (!window.confirm(`确定删除“${draft.name || "这个数据源"}”吗？历史执行记录会保留。`)) return;
    try {
      await api(`/data-sources/${draft.id}`, { method: "DELETE" });
      await reload();
      setStatus(`已删除“${draft.name || "数据源"}”，历史执行记录已保留。`);
    } catch (error) { setStatus(error instanceof Error ? error.message : "删除数据源失败"); }
  };

  return (
    <div className="page-stack subpage">
      <section className="subpage-title"><div><p className="section-kicker">数据源与自动化</p><h1>一条数据源，就是一个可维护的脚本。</h1><p>同一个基金脚本可绑定多项基金，一次查询后分别更新对应字段。</p></div><span className="runner-badge"><i />Python 3 · uv · Git 版本</span></section>
      <section className="automation-workspace">
        <aside className="panel source-library">
          <div className="source-library-head"><div><strong>脚本库</strong><small>{sources.length} 个数据源</small></div><button type="button" onClick={() => { setDraft(freshDataSource()); setStatus("正在创建新数据源。"); }}>＋ 新建</button></div>
          <div className="source-list">
            {sources.map((source) => (
              <button type="button" key={source.id} className={draft.id === source.id ? "source-card active" : "source-card"} onClick={() => { setDraft(source); setStatus(""); }}>
                <span className={`source-state ${source.lastStatus || "idle"}`} />
                <span><strong>{source.name}</strong><small>{source.assetIds.length} 项资产 · {source.scheduleMinutes < 1440 ? `${source.scheduleMinutes} 分钟` : `${source.scheduleMinutes / 1440} 天`}</small></span>
                <em>{source.enabled ? "自动" : "手动"}</em>
              </button>
            ))}
            {sources.length === 0 && <p className="empty-copy">保存右侧脚本后，它会出现在这里。</p>}
          </div>
          <div className="source-library-note"><strong>脚本可以更新</strong><span>单价、汇率、数据源自定义属性</span><small>资产 ID、名称与所属篮子不由脚本修改。</small></div>
        </aside>

        <div className="source-detail">
          <section className="panel source-config">
            <div className="source-detail-head"><div><p className="section-kicker">{draft.id ? "编辑数据源" : "新数据源"}</p><h2>{draft.name || "未命名脚本"}</h2><small>{draft.gitRevision ? `Git ${draft.gitRevision.slice(0, 8)}` : "首次保存时建立 Git 版本"}{draft.lastRunAt ? ` · 上次运行 ${new Date(draft.lastRunAt).toLocaleString("zh-CN")}` : ""}</small></div><div className="source-actions">{draft.id && <button className="danger-button" type="button" onClick={deleteSource}>删除数据源</button>}<button type="button" onClick={runSource}>立即执行</button><button className="primary-button" type="button" onClick={saveSource}>保存版本</button></div></div>
            <div className="source-basic-grid">
              <label>数据源名称<input value={draft.name} onChange={(event) => changeDraft("name", event.target.value)} /></label>
              <label>入口函数<input value={draft.functionName} onChange={(event) => changeDraft("functionName", event.target.value)} /></label>
              <label>调度间隔（分钟）<input type="number" min="1" max="525600" value={draft.scheduleMinutes} onChange={(event) => changeDraft("scheduleMinutes", Number(event.target.value))} /></label>
              <label className="source-enabled"><input type="checkbox" checked={draft.enabled} onChange={(event) => changeDraft("enabled", event.target.checked)} /><span>启用自动调度<small>关闭时仍可手动执行</small></span></label>
              <label className="wide-field">描述<textarea value={draft.description} onChange={(event) => changeDraft("description", event.target.value)} /></label>
            </div>
          </section>

          <section className="automation-summary" aria-label="脚本执行摘要"><span>脚本运行 1 次 · 处理 {draft.assetIds.length} 项资产 · 按 <code>asset_id</code> 更新结果</span><button type="button" onClick={() => setShowFieldGuide(true)}>字段说明</button></section>

          <section className="panel source-bindings">
            <PanelHeading title="1. 选择由此脚本更新的资产" subtitle="每个勾选项都会作为一条记录传入脚本；资产名称和所属篮子不会被脚本修改" action={`${draft.assetIds.length} 项已选`} />
            <div className={selectedAssets.length ? "selected-assets" : "selected-assets empty"}><strong>{selectedAssets.length ? "本次会传入：" : "尚未选择资产"}</strong><span>{selectedAssets.length ? `${selectedAssets.map((asset) => asset.name).join("、")}。脚本只运行 1 次，payload.items 中包含 ${selectedAssets.length} 条资产记录。` : "请先勾选本次需要查询的基金、股票或数字资产。"}</span></div>
            <div className="asset-check-grid">
              {assets.map((asset) => (
                <label key={asset.id} className={draft.assetIds.includes(asset.id) ? "checked" : ""}>
                  <input type="checkbox" checked={draft.assetIds.includes(asset.id)} onChange={(event) => changeDraft("assetIds", event.target.checked ? [...draft.assetIds, asset.id] : draft.assetIds.filter((id) => id !== asset.id))} />
                  <span><strong>{asset.name}</strong><small>{asset.platform} · {asset.symbol || "无代码"}</small></span><em>{asset.basketName}</em>
                </label>
              ))}
            </div>
          </section>

          <section className="panel mapping-workspace">
            <MappingEditor title="2. 每项资产提供给脚本的资料" value={draft.inputMapping} onChange={(value) => changeDraft("inputMapping", value)} />
            <MappingEditor title="3. 脚本结果要更新的资产资料" value={draft.outputMapping} onChange={(value) => changeDraft("outputMapping", value)} output />
          </section>

          <section className="panel editor-panel source-editor">
            <div className="editor-toolbar"><span><i className="red" /><i className="yellow" /><i className="green" /></span><strong>{draft.name || "source"}.py</strong><small>Python 3 · uv</small></div>
            <textarea aria-label="Python 数据源代码" value={draft.code} onChange={(event) => changeDraft("code", event.target.value)} spellCheck={false} />
            <div className="editor-footer"><label>依赖包（逗号分隔）<input value={draft.packages.join(", ")} onChange={(event) => changeDraft("packages", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="httpx, pandas" /></label><span>保存会建立新的 Git 回退点</span><button className="primary-button" type="button" onClick={saveSource}>保存版本</button></div>
            {status && <p className="editor-status">{status}</p>}
          </section>
        </div>
      </section>
      {showFieldGuide && <FieldGuide selectedCount={draft.assetIds.length} onClose={() => setShowFieldGuide(false)} />}
    </div>
  );
}

function SettingsView({ data, onChanged }: { data: Dashboard; onChanged: () => Promise<void> }) {
  const emergencyBasket = data.baskets.find((basket) => basket.code === "emergency");
  const [config, setConfig] = useState<PlatformConfig>({
    allocationMode: data.allocation.mode,
    growthRatio: data.allocation.targetGrowthRatio / 100,
    riskRatio: data.allocation.targetRiskRatio / 100,
    defaultContributionCny: data.allocation.defaultContributionCny,
    emergencyTargetCny: emergencyBasket?.emergencyTargetCny ?? 0,
    emergencyCalculationNote: emergencyBasket?.calculationNote ?? "",
  });
  const [rules, setRules] = useState<NotificationRuleView[]>([]);
  const [message, setMessage] = useState("");
  const [expenses, setExpenses] = useState({ rent: 0, food: 0, utilities: 0, transport: 0, insurance: 0, other: 0, months: 6 });
  const [ruleDraft, setRuleDraft] = useState({
    id: "", name: "总资产达到 30 万", metricPath: "portfolio.total_asset_cny", operator: ">=" as NotificationRuleView["operator"], threshold: "300000",
    webhookUrl: "", headers: "{}", bodyTemplate: '{"title":"{{event.title}}","message":"{{event.message}}","currentValue":"{{event.currentValue}}","triggeredAt":"{{event.triggeredAt}}"}',
    windowHours: "24", maxDeliveries: "1", enabled: true,
  });

  useEffect(() => {
    let active = true;
    Promise.all([api<PlatformConfig>("/settings"), api<NotificationRuleView[]>("/notification-rules")])
      .then(([settings, notificationRules]) => { if (active) { setConfig(settings); setRules(notificationRules); } })
      .catch((error) => { if (active) setMessage(error instanceof Error ? error.message : "设置读取失败"); });
    return () => { active = false; };
  }, []);

  const monthlyExpense = expenses.rent + expenses.food + expenses.utilities + expenses.transport + expenses.insurance + expenses.other;
  const suggestedReserve = Math.ceil(monthlyExpense * expenses.months / 1000) * 1000;
  const updateExpense = (key: keyof typeof expenses, value: number) => setExpenses((current) => ({ ...current, [key]: value }));

  const saveAllocation = async () => {
    try {
      if (Math.abs(config.growthRatio + config.riskRatio - 1) > 0.000001) throw new Error("成长与高风险比例之和必须是 100%");
      const saved = await api<PlatformConfig>("/settings", { method: "PATCH", body: JSON.stringify({
        allocation_mode: config.allocationMode, growth_ratio: config.growthRatio,
        risk_ratio: config.riskRatio, default_contribution_cny: config.defaultContributionCny,
      }) });
      setConfig(saved); setMessage("流入与配置策略已保存"); await onChanged();
    } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); }
  };

  const saveEmergency = async () => {
    try {
      await api("/baskets/emergency", { method: "PATCH", body: JSON.stringify({
        emergency_target_cny: config.emergencyTargetCny,
        calculation_note: config.emergencyCalculationNote,
      }) });
      setMessage("应急储备金目标与计算备注已保存"); await onChanged();
    } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); }
  };

  const loadRules = async () => setRules(await api<NotificationRuleView[]>("/notification-rules"));
  const editRule = (rule: NotificationRuleView) => setRuleDraft({
    id: rule.id, name: rule.name, metricPath: rule.metricPath, operator: rule.operator,
    threshold: rule.threshold === null ? "" : String(rule.threshold), webhookUrl: rule.webhookUrl,
    headers: JSON.stringify(rule.headersJson ?? {}, null, 2), bodyTemplate: rule.bodyTemplate,
    windowHours: String(rule.windowSeconds / 3600), maxDeliveries: String(rule.maxDeliveries), enabled: rule.enabled,
  });
  const newRule = () => setRuleDraft({
    id: "", name: "总资产达到 30 万", metricPath: "portfolio.total_asset_cny", operator: ">=", threshold: "300000", webhookUrl: "", headers: "{}",
    bodyTemplate: '{"title":"{{event.title}}","message":"{{event.message}}","currentValue":"{{event.currentValue}}","triggeredAt":"{{event.triggeredAt}}"}', windowHours: "24", maxDeliveries: "1", enabled: true,
  });
  const saveRule = async () => {
    try {
      const headers = JSON.parse(ruleDraft.headers || "{}");
      if (!ruleDraft.webhookUrl.trim()) throw new Error("请填写 Webhook URL");
      const payload = {
        name: ruleDraft.name, event_type: "generic_metric", metric_path: ruleDraft.metricPath,
        operator: ruleDraft.operator, threshold: ruleDraft.threshold || null, webhook_url: ruleDraft.webhookUrl,
        headers_json: headers, body_template: ruleDraft.bodyTemplate,
        window_seconds: Math.max(1, Number(ruleDraft.windowHours)) * 3600,
        max_deliveries: Math.max(1, Number(ruleDraft.maxDeliveries)), enabled: ruleDraft.enabled,
      };
      const saved = await api<{ id: string }>(ruleDraft.id ? `/notification-rules/${ruleDraft.id}` : "/notification-rules", {
        method: ruleDraft.id ? "PATCH" : "POST", body: JSON.stringify(payload),
      });
      await loadRules(); setRuleDraft((current) => ({ ...current, id: saved.id })); setMessage("外部推送连接已保存");
    } catch (error) { setMessage(error instanceof Error ? error.message : "推送设置保存失败"); }
  };
  const toggleRule = async (rule: NotificationRuleView) => {
    try { await api(`/notification-rules/${rule.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !rule.enabled }) }); await loadRules(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "状态更新失败"); }
  };
  const testRule = async () => {
    if (!ruleDraft.id) { setMessage("请先保存推送连接再测试"); return; }
    try { const result = await api<{ status: string }>(`/notification-rules/${ruleDraft.id}/test`, { method: "POST" }); setMessage(`测试推送状态：${result.status}`); }
    catch (error) { setMessage(error instanceof Error ? error.message : "测试推送失败"); }
  };
  const deleteRule = async () => {
    if (!ruleDraft.id) return;
    if (!window.confirm(`确定删除“${ruleDraft.name || "这个推送规则"}”吗？历史推送记录会保留。`)) return;
    try {
      await api(`/notification-rules/${ruleDraft.id}`, { method: "DELETE" });
      await loadRules();
      newRule();
      setMessage(`已删除“${ruleDraft.name || "推送规则"}”，历史推送记录已保留。`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "删除推送规则失败"); }
  };

  return (
    <div className="page-stack subpage settings-page">
      <section className="subpage-title"><div><p className="section-kicker">平台设置</p><h1>把日常规则定下来，剩下的交给记录。</h1><p>配置每月流入策略、应急储备目标和外部推送连接。</p></div></section>
      {message && <button className="inline-message settings-message" type="button" onClick={() => setMessage("")}>{message}<span>×</span></button>}
      <section className="settings-grid">
        <div className="panel settings-card allocation-settings">
          <PanelHeading title="每月资金流入" subtitle="应急储备金不足时优先补足" action={config.allocationMode === "dynamic" ? "动态平衡" : "固定比例"} />
          <div className="settings-body">
            <div className="strategy-choice">
              <button type="button" className={config.allocationMode === "dynamic" ? "active" : ""} onClick={() => setConfig((current) => ({ ...current, allocationMode: "dynamic" }))}><strong>动态平衡</strong><span>只根据已更新的持仓价值纠正篮子比例</span></button>
              <button type="button" className={config.allocationMode === "fixed" ? "active" : ""} onClick={() => setConfig((current) => ({ ...current, allocationMode: "fixed" }))}><strong>固定比例</strong><span>每次流入直接按目标比例分配</span></button>
            </div>
            <div className="setting-form three-columns">
              <label>默认每月流入<input type="number" min="0" value={config.defaultContributionCny} onChange={(event) => setConfig((current) => ({ ...current, defaultContributionCny: Number(event.target.value) }))} /></label>
              <label>成长篮子（%）<input type="number" min="0" max="100" step="0.1" value={config.growthRatio * 100} onChange={(event) => setConfig((current) => ({ ...current, growthRatio: Number(event.target.value) / 100 }))} /></label>
              <label>高风险篮子（%）<input type="number" min="0" max="100" step="0.1" value={config.riskRatio * 100} onChange={(event) => setConfig((current) => ({ ...current, riskRatio: Number(event.target.value) / 100 }))} /></label>
            </div>
            <p className="setting-note">待购买现金不参与篮子比例计算；它会保留在对应篮子中，直到记录实际买入。</p>
            <div className="settings-actions"><button className="primary-button" type="button" onClick={saveAllocation}>保存配置策略</button></div>
          </div>
        </div>

        <div className="panel settings-card emergency-settings">
          <PanelHeading title="应急储备金" subtitle="在这里计算并保存储备目标" action={money(config.emergencyTargetCny, true)} />
          <div className="settings-body">
            <div className="expense-grid">
              {([["房租 / 房贷", "rent"], ["伙食", "food"], ["水电网", "utilities"], ["交通", "transport"], ["保险与医疗", "insurance"], ["其他必要支出", "other"]] as [string, keyof typeof expenses][]).map(([label, key]) => (
                <label key={key}>{label}<input type="number" min="0" value={expenses[key]} onChange={(event) => updateExpense(key, Number(event.target.value))} /></label>
              ))}
              <label>覆盖月数<input type="number" min="1" max="36" value={expenses.months} onChange={(event) => updateExpense("months", Number(event.target.value))} /></label>
            </div>
            <div className="reserve-suggestion"><span>每月必要支出 {money(monthlyExpense, true)}</span><strong>建议储备 {money(suggestedReserve, true)}</strong><small>按 {expenses.months} 个月计算，已向上取整到千元</small><button type="button" onClick={() => setConfig((current) => ({ ...current, emergencyTargetCny: suggestedReserve, emergencyCalculationNote: `每月必要支出 ${monthlyExpense.toFixed(0)} 元 × ${expenses.months} 个月，向上取整到千元。` }))}>采用建议金额</button></div>
            <div className="setting-form">
              <label>最终储备目标<input type="number" min="0" step="1000" value={config.emergencyTargetCny} onChange={(event) => setConfig((current) => ({ ...current, emergencyTargetCny: Number(event.target.value) }))} /></label>
              <label>计算口径与备注<textarea value={config.emergencyCalculationNote} onChange={(event) => setConfig((current) => ({ ...current, emergencyCalculationNote: event.target.value }))} placeholder="例如：不含年度旅行支出" /></label>
            </div>
            <div className="settings-actions"><button className="primary-button" type="button" onClick={saveEmergency}>保存储备目标</button></div>
          </div>
        </div>
      </section>

      <section className="panel settings-card webhook-settings">
        <div className="webhook-settings-head"><PanelHeading title="外部推送连接" subtitle="用 URL、Header 和占位符模板发送事件" action={`${rules.length} 条规则`} /><button type="button" onClick={newRule}>＋ 新建规则</button></div>
        <div className="webhook-settings-grid">
          <div className="webhook-rule-list">
            {rules.map((rule) => (
              <div className={ruleDraft.id === rule.id ? "webhook-rule-card active" : "webhook-rule-card"} key={rule.id}>
                <button className="webhook-rule-main" type="button" onClick={() => editRule(rule)}><span className="webhook-icon">↗</span><span><strong>{rule.name}</strong><small>{rule.metricPath} {rule.operator} {rule.threshold ?? "事件值"}</small><em>{rule.windowSeconds / 3600} 小时内最多 {rule.maxDeliveries} 次</em></span></button>
                <button type="button" className={rule.enabled ? "switch on" : "switch"} aria-label={rule.enabled ? "停用推送" : "启用推送"} onClick={() => toggleRule(rule)} />
              </div>
            ))}
            {rules.length === 0 && <p className="empty-copy">还没有推送规则。</p>}
          </div>
          <div className="webhook-editor">
            <div className="webhook-editor-title"><strong>{ruleDraft.id ? "编辑推送规则" : "新建推送规则"}</strong><span>可使用 <code>{"{{event.title}}"}</code>、<code>{"{{event.currentValue}}"}</code>、<code>{"{{event.triggeredAt}}"}</code></span></div>
            <div className="setting-form webhook-fields">
              <label>规则名称<input value={ruleDraft.name} onChange={(event) => setRuleDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <label>数据路径<input value={ruleDraft.metricPath} onChange={(event) => setRuleDraft((current) => ({ ...current, metricPath: event.target.value }))} /></label>
              <label>比较方式<select value={ruleDraft.operator} onChange={(event) => setRuleDraft((current) => ({ ...current, operator: event.target.value as NotificationRuleView["operator"] }))}><option>&gt;=</option><option>&gt;</option><option>&lt;=</option><option>&lt;</option><option>=</option></select></label>
              <label>触发值<input type="number" step="any" value={ruleDraft.threshold} onChange={(event) => setRuleDraft((current) => ({ ...current, threshold: event.target.value }))} /></label>
              <label className="wide-field">Webhook URL<input type="url" value={ruleDraft.webhookUrl} onChange={(event) => setRuleDraft((current) => ({ ...current, webhookUrl: event.target.value }))} placeholder="https://example.com/webhook" /></label>
              <label className="wide-field">Headers（JSON）<textarea value={ruleDraft.headers} onChange={(event) => setRuleDraft((current) => ({ ...current, headers: event.target.value }))} /></label>
              <label>窗口（小时）<input type="number" min="0.01" step="any" value={ruleDraft.windowHours} onChange={(event) => setRuleDraft((current) => ({ ...current, windowHours: event.target.value }))} /></label>
              <label>窗口内最多次数<input type="number" min="1" value={ruleDraft.maxDeliveries} onChange={(event) => setRuleDraft((current) => ({ ...current, maxDeliveries: event.target.value }))} /></label>
              <label className="wide-field">消息模板<textarea value={ruleDraft.bodyTemplate} onChange={(event) => setRuleDraft((current) => ({ ...current, bodyTemplate: event.target.value }))} /></label>
            </div>
            <div className="settings-actions">{ruleDraft.id && <button className="danger-button" type="button" onClick={deleteRule}>删除推送规则</button>}<button type="button" onClick={testRule}>发送测试</button><button className="primary-button" type="button" onClick={saveRule}>保存推送规则</button></div>
          </div>
        </div>
      </section>
    </div>
  );
}

function AchievementsView({ data }: { data: Dashboard }) {
  const goal = data.goals[0];
  const rings = useMemo(() => [
    { title: "开始记录", date: "2026.02.10", note: "种下第一颗种子", state: "done" },
    { title: "应急底座", date: "2026.06.18", note: "六个月储备完成", state: "done" },
    { title: "第一片树荫", date: goal ? `${Math.round(goal.progress)}%` : "进行中", note: "目标 30 万", state: "active" },
    { title: "下一圈年轮", date: "尚未设定", note: "留给未来的自己", state: "future" },
  ], [goal]);
  return (
    <div className="page-stack subpage achievement-page">
      <section className="subpage-title"><div><p className="section-kicker">我的成长纪事</p><h1>不是数字变大，是生活的边界变宽。</h1><p>每一次达成都会永久留在年轮里。</p></div><button className="primary-button">＋ 新建里程碑</button></section>
      {goal && (
        <section className="panel achievement-hero">
          <div className="achievement-emblem"><span>木</span><i /></div>
          <div className="achievement-copy"><p>正在生长</p><h2>{goal.title}</h2><p>总资产达到 {money(goal.targetAmountCny, true)}，拥有更从容的选择空间。</p><div className="wide-progress"><i style={{ width: `${goal.progress}%` }} /></div><div className="achievement-meta"><span>{percent(goal.progress)} 已完成</span><span>还差 {money(goal.remainingCny, true)}</span></div></div>
          <div className="reward-box"><small>给自己的奖励</small><strong>{goal.rewardTitle}</strong><p>{goal.rewardDescription}</p><span>达成时开启</span></div>
        </section>
      )}
      <section className="panel timeline-panel">
        <PanelHeading title="资产年轮" subtitle="时间不会删除已经完成的事" action="2 项已解锁" />
        <div className="achievement-timeline">
          {rings.map((ring, index) => (
            <div className={`timeline-item ${ring.state}`} key={ring.title}><div className="timeline-mark">{ring.state === "done" ? "✓" : index + 1}</div><div><small>{ring.date}</small><strong>{ring.title}</strong><p>{ring.note}</p></div></div>
          ))}
        </div>
      </section>
    </div>
  );
}
