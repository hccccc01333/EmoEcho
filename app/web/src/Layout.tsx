import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { MessageCircle, User, BarChart3, Settings, Archive, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import AmbientBackground from './components/AmbientBackground';
import PetWidget from './components/PetWidget';

const NAV = [
  { to: '/', icon: MessageCircle, label: '对话' },
  { to: '/profile', icon: User, label: '人格' },
  { to: '/insights', icon: BarChart3, label: '洞察' },
  { to: '/settings', icon: Settings, label: '设置' },
];

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-screen relative">
      <AmbientBackground />

      {/* Sidebar */}
      <motion.nav
        animate={{ width: collapsed ? 64 : 200 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="relative z-10 flex flex-col py-5 border-r border-white/[0.06] bg-black/20 backdrop-blur-xl shrink-0"
      >
        {/* Brand */}
        <div className={clsx('flex items-center gap-2.5 mb-8', collapsed ? 'justify-center px-2' : 'px-5')}>
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500 to-accent-violet flex items-center justify-center text-white font-display font-bold text-sm shadow-lg shadow-brand-600/20">
            E
          </div>
          {!collapsed && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="font-display font-semibold text-sm text-gray-200 tracking-tight"
            >
              EmoEcho
            </motion.span>
          )}
        </div>

        {/* Nav items */}
        <div className="flex-1 flex flex-col gap-1 px-2">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 rounded-xl text-sm transition-all duration-200',
                  collapsed ? 'justify-center px-2 py-2.5' : 'px-3.5 py-2.5',
                  isActive
                    ? 'bg-white/[0.10] text-white shadow-sm'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.04]',
                )
              }
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </div>

        {/* Collapse toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="mx-2 mt-2 flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-gray-600 hover:text-gray-400 hover:bg-white/[0.04] transition-colors text-xs"
        >
          {collapsed ? <ChevronRight size={14} /> : <><ChevronLeft size={14} /><span>收起</span></>}
        </button>
      </motion.nav>

      {/* Main content */}
      <main className="flex-1 overflow-hidden relative z-10">
        <Outlet />
      </main>

      {/* Pet widget */}
      <PetWidget mood="calm" />
    </div>
  );
}
