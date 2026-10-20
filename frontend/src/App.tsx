import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { EmptyState } from "./components/States";
import { OverviewPage } from "./pages/OverviewPage";

function NotFound() {
  return <EmptyState title="Page not found">Use the navigation to choose a page.</EmptyState>;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout title="Overview"><OverviewPage /></Layout>} />
      <Route path="*" element={<Layout title="Not found"><NotFound /></Layout>} />
    </Routes>
  );
}
