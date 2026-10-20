import { Suspense, lazy, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { EmptyState, Loading } from "./components/States";

// Pages are code-split so each route downloads only what it needs.
const OverviewPage = lazy(() => import("./pages/OverviewPage").then((m) => ({ default: m.OverviewPage })));
const ExplorePage = lazy(() => import("./pages/ExplorePage").then((m) => ({ default: m.ExplorePage })));
const ComparePage = lazy(() => import("./pages/ComparePage").then((m) => ({ default: m.ComparePage })));
const RunsPage = lazy(() => import("./pages/RunsPage").then((m) => ({ default: m.RunsPage })));
const RunDetailPage = lazy(() => import("./pages/RunDetailPage").then((m) => ({ default: m.RunDetailPage })));
const QualityPage = lazy(() => import("./pages/QualityPage").then((m) => ({ default: m.QualityPage })));
const AboutPage = lazy(() => import("./pages/AboutPage").then((m) => ({ default: m.AboutPage })));

function NotFound() {
  return <EmptyState title="Page not found">Use the navigation to choose a page.</EmptyState>;
}

function page(title: string, element: ReactNode) {
  return (
    <Layout title={title}>
      <Suspense fallback={<Loading />}>{element}</Suspense>
    </Layout>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={page("Overview", <OverviewPage />)} />
      <Route path="/explore" element={page("Explore Data", <ExplorePage />)} />
      <Route path="/compare" element={page("Compare Countries", <ComparePage />)} />
      <Route path="/runs" element={page("Pipeline Runs", <RunsPage />)} />
      <Route path="/runs/:runId" element={page("Run Details", <RunDetailPage />)} />
      <Route path="/quality" element={page("Data Quality", <QualityPage />)} />
      <Route path="/about" element={page("About & Sources", <AboutPage />)} />
      <Route path="*" element={page("Not found", <NotFound />)} />
    </Routes>
  );
}
