import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { SessionsPage } from "./pages/SessionsPage";
import { AlertsPage } from "./pages/AlertsPage";
import { LivePage } from "./pages/LivePage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/sessions" replace />} />
        <Route element={<Layout />}>
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="sessions/:sessionId/alerts" element={<AlertsPage />} />
          <Route path="sessions/:sessionId/live" element={<LivePage />} />
        </Route>
        <Route path="*" element={<Navigate to="/sessions" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
