import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { Health } from "../api/types";
import { useLastRefresh } from "../hooks/useLastRefresh";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/explore", label: "Explore Data" },
  { to: "/compare", label: "Compare Countries" },
  { to: "/runs", label: "Pipeline Runs" },
  { to: "/quality", label: "Data Quality" },
  { to: "/about", label: "About & Sources" },
];

function HealthIndicator() {
  const [health, setHealth] = useState<{ api: boolean; db: boolean } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const check = () =>
      fetch("/health", { signal: controller.signal })
        .then(async (r) => {
          const body = (await r.json().catch(() => null)) as Health | null;
          setHealth({ api: true, db: r.ok && body?.database === "ok" });
        })
        .catch((e: unknown) => {
          if (!(e instanceof DOMException && e.name === "AbortError")) setHealth({ api: false, db: false });
        });
    void check();
    const timer = window.setInterval(check, 30000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, []);
  if (!health) return <span className="health muted">Checking backend…</span>;
  return (
    <span className={`health ${health.api && health.db ? "health-ok" : "health-bad"}`} role="status">
      <span aria-hidden="true">{health.api && health.db ? "●" : "▲"}</span> API {health.api ? "online" : "offline"} · Database{" "}
      {health.db ? "ok" : "unavailable"}
    </span>
  );
}

export function LastRefresh() {
  const at = useLastRefresh();
  if (!at) return <span className="muted refresh">Not refreshed yet</span>;
  const time = at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return (
    <span className="muted refresh">
      Last refresh{" "}
      <time dateTime={at.toISOString()} title={at.toLocaleString("en-GB")}>
        {time}
      </time>
    </span>
  );
}

export function Layout({ title, children }: { title: string; children: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · Global Economic Data Pipeline`;
  }, [title]);
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">GE</span>
          <span>
            Global Economic
            <br />
            Data Pipeline
          </span>
        </div>
        <nav aria-label="Main">
          <ul>
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="sidebar-footer">
          v{__APP_VERSION__} · Data: World Bank
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1>{title}</h1>
          <div className="topbar-status" aria-live="polite">
            <LastRefresh />
            <HealthIndicator />
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
