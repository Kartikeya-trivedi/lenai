import React, { useState } from 'react';
import { Send, Image as ImageIcon, Mic, Video, Type } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function OmniInput({ onSubmit, isLoading }) {
  const [text, setText] = useState('');
  const [modality, setModality] = useState('text'); // text, image, voice, video

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!text.trim() || isLoading) return;
    onSubmit(text, modality);
    setText('');
  };

  const getPlaceholder = () => {
    switch(modality) {
      case 'image': return 'Describe the stunning image you want to generate...';
      case 'voice': return 'Type the text you want converted to beautiful speech...';
      case 'video': return 'Describe the video scene... (Coming soon)';
      default: return 'Ask a question or type your message...';
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto p-4 md:px-8">
      <motion.form 
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        onSubmit={handleSubmit} 
        className="relative glass-panel rounded-3xl p-3 flex flex-col gap-3 shadow-[0_10px_40px_rgba(0,0,0,0.5)]"
      >
        {/* Modality Selector */}
        <div className="flex flex-wrap gap-2 px-3 pt-1">
          <button type="button" onClick={() => setModality('text')} className={`px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-all duration-300 ${modality === 'text' ? 'bg-indigo-500/20 text-indigo-300 shadow-[0_0_15px_rgba(99,102,241,0.2)] scale-105' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}>
            <Type size={16} /> Chat
          </button>
          <button type="button" onClick={() => setModality('image')} className={`px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-all duration-300 ${modality === 'image' ? 'bg-purple-500/20 text-purple-300 shadow-[0_0_15px_rgba(168,85,247,0.2)] scale-105' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}>
            <ImageIcon size={16} /> Image
          </button>
          <button type="button" onClick={() => setModality('voice')} className={`px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-all duration-300 ${modality === 'voice' ? 'bg-emerald-500/20 text-emerald-300 shadow-[0_0_15px_rgba(16,185,129,0.2)] scale-105' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}>
            <Mic size={16} /> Voice
          </button>
          <button type="button" onClick={() => setModality('video')} className={`px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-all duration-300 ${modality === 'video' ? 'bg-orange-500/20 text-orange-300 shadow-[0_0_15px_rgba(249,115,22,0.2)] scale-105' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}>
            <Video size={16} /> Video
          </button>
        </div>

        {/* Input Area */}
        <div className="flex items-end gap-3 relative px-1">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={getPlaceholder()}
            className="w-full bg-black/40 text-slate-100 placeholder-slate-500 rounded-2xl px-5 py-4 min-h-[64px] max-h-[250px] resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500/50 transition-shadow text-base"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
          />
          <AnimatePresence>
            {text.trim() && !isLoading && (
              <motion.button 
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                type="submit" 
                className="absolute right-4 bottom-3 p-3 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 text-white shadow-lg transition-all"
              >
                <Send size={20} />
              </motion.button>
            )}
          </AnimatePresence>
          {isLoading && (
             <button disabled className="absolute right-4 bottom-3 p-3 rounded-xl bg-indigo-600/50 text-white cursor-not-allowed">
               <Send size={20} className="opacity-50" />
             </button>
          )}
        </div>
      </motion.form>
    </div>
  );
}
