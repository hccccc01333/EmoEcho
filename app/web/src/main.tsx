import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './index.css';
import Layout from './Layout';
import ChatPage from './pages/ChatPage';
import ProfilePage from './pages/ProfilePage';
import InsightDashboard from './pages/InsightDashboard';
import ArchivePage from './pages/ArchivePage';
import SettingsPage from './pages/SettingsPage';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/insights" element={<InsightDashboard />} />
          <Route path="/archive/:slug" element={<ArchivePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
