import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Bot, User, Image as ImageIcon, Loader2 } from 'lucide-react';

export default function MessageBubble({ role, content, modality, mediaUrl, status }) {
  const isUser = role === 'user';

  return (
    <div className={`flex w-full mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start gap-3`}>
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${isUser ? 'bg-indigo-600' : 'bg-slate-800 border border-slate-700'}`}>
          {isUser ? <User size={16} className="text-white" /> : <Bot size={16} className="text-indigo-400" />}
        </div>
        
        <div className={`glass-panel p-4 rounded-2xl ${isUser ? 'rounded-tr-sm bg-indigo-900/20' : 'rounded-tl-sm'}`}>
          {status === 'processing' && (
            <div className="flex items-center gap-2 text-indigo-400">
              <Loader2 className="animate-spin" size={16} />
              <span className="text-sm font-medium">Processing...</span>
            </div>
          )}
          
          {content && (
            <div className="prose prose-invert max-w-none text-sm">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}

          {modality === 'image' && status === 'completed' && mediaUrl && (
            <div className="mt-3 rounded-lg overflow-hidden border border-border">
              <img src={mediaUrl} alt="Generated" className="max-w-full h-auto object-contain max-h-[400px]" />
            </div>
          )}
          
          {status === 'failed' && (
            <div className="mt-2 text-red-400 text-xs">Failed to generate response.</div>
          )}
        </div>
      </div>
    </div>
  );
}
