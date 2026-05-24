import React, { useState } from 'react';
import { Send, Image as ImageIcon, Mic, Video, Type } from 'lucide-react';

export default function OmniInput({ onSubmit, isLoading }) {
  const [text, setText] = useState('');
  const [modality, setModality] = useState('text'); // text, image, voice, video

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!text.trim() || isLoading) return;
    onSubmit(text, modality);
    setText('');
  };

  return (
    <div className="w-full max-w-4xl mx-auto p-4">
      <form onSubmit={handleSubmit} className="relative glass-panel rounded-2xl p-2 flex flex-col gap-2">
        {/* Modality Selector */}
        <div className="flex gap-2 px-2 pt-1">
          <button type="button" onClick={() => setModality('text')} className={`p-2 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors ${modality === 'text' ? 'bg-indigo-500/20 text-indigo-300' : 'text-slate-400 hover:text-slate-200'}`}>
            <Type size={14} /> Chat
          </button>
          <button type="button" onClick={() => setModality('image')} className={`p-2 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors ${modality === 'image' ? 'bg-purple-500/20 text-purple-300' : 'text-slate-400 hover:text-slate-200'}`}>
            <ImageIcon size={14} /> Image
          </button>
          <button type="button" onClick={() => setModality('voice')} className={`p-2 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors ${modality === 'voice' ? 'bg-emerald-500/20 text-emerald-300' : 'text-slate-400 hover:text-slate-200'}`}>
            <Mic size={14} /> Voice
          </button>
          <button type="button" onClick={() => setModality('video')} className={`p-2 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors ${modality === 'video' ? 'bg-orange-500/20 text-orange-300' : 'text-slate-400 hover:text-slate-200'}`}>
            <Video size={14} /> Video
          </button>
        </div>

        {/* Input Area */}
        <div className="flex items-end gap-2 relative">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              modality === 'image' ? 'Describe the image you want to generate...' :
              modality === 'voice' ? 'What do you want to say?' :
              'Type your message...'
            }
            className="w-full bg-transparent text-slate-200 placeholder-slate-500 px-4 py-3 min-h-[56px] max-h-[200px] resize-none focus:outline-none text-sm"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
          />
          <button 
            type="submit" 
            disabled={!text.trim() || isLoading}
            className="absolute right-2 bottom-2 p-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 disabled:hover:bg-indigo-600 transition-all"
          >
            <Send size={18} />
          </button>
        </div>
      </form>
    </div>
  );
}
