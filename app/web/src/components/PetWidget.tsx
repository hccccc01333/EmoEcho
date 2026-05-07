import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageCircle, X } from 'lucide-react';

interface PetWidgetProps {
  mood?: 'happy' | 'calm' | 'energetic' | 'sad';
  lastMessage?: string;
}

const MOOD_COLORS: Record<string, string> = {
  happy: '#f59e0b',
  calm: '#3b82f6',
  energetic: '#ec4899',
  sad: '#8b5cf6',
};

export default function PetWidget({ mood = 'calm', lastMessage }: PetWidgetProps) {
  const [open, setOpen] = useState(false);
  const ringColor = MOOD_COLORS[mood] || MOOD_COLORS.calm;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Mini chat bubble */}
      <AnimatePresence>
        {open && lastMessage && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            className="glass-card p-3 max-w-[240px] relative"
          >
            <button
              onClick={() => setOpen(false)}
              className="absolute top-1.5 right-1.5 text-gray-600 hover:text-gray-400"
            >
              <X size={12} />
            </button>
            <p className="text-xs text-gray-300 leading-relaxed pr-4">{lastMessage}</p>
            <div className="absolute bottom-[-6px] right-8 w-3 h-3 rotate-45 bg-white/[0.06] border-r border-b border-white/[0.08]" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Pet avatar */}
      <motion.button
        onClick={() => setOpen(!open)}
        className="relative w-[72px] h-[72px] rounded-full cursor-pointer"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        {/* Emotion aura ring */}
        <div
          className="absolute inset-[-4px] rounded-full opacity-60 transition-colors duration-1000"
          style={{ boxShadow: `0 0 20px 4px ${ringColor}40, inset 0 0 20px 4px ${ringColor}20` }}
        />
        {/* Avatar body */}
        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-brand-600 to-brand-700 flex items-center justify-center animate-breathe shadow-lg shadow-brand-600/20">
          <span className="text-2xl select-none">🐾</span>
        </div>
        {/* Notification dot */}
        {lastMessage && !open && (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute top-0 right-0 w-4 h-4 bg-accent-amber rounded-full flex items-center justify-center"
          >
            <MessageCircle size={8} className="text-black" />
          </motion.div>
        )}
      </motion.button>
    </div>
  );
}
