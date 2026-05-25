import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Bot, User, Image as ImageIcon, Loader2, Music } from 'lucide-react';
import { motion } from 'framer-motion';

export default function MessageBubble({ role, content, modality, mediaUrl, status, errorMessage }) {
  const isUser = role === 'user';

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.23, 1, 0.32, 1] }}
      className={`flex w-full mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div className={`flex max-w-[85%] md:max-w-[75%] ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start gap-4`}>
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center shadow-lg ${isUser ? 'bg-gradient-to-br from-indigo-500 to-purple-600' : 'bg-slate-800 border border-slate-700'}`}>
          {isUser ? <User size={16} className="text-white" /> : <Bot size={16} className="text-indigo-400" />}
        </div>
        
        <div className={`glass-panel p-5 rounded-2xl ${isUser ? 'rounded-tr-sm bg-indigo-900/30' : 'rounded-tl-sm'}`}>
          {status === 'processing' && (
            <div className="flex items-center gap-3 text-indigo-400">
              <Loader2 className="animate-spin" size={18} />
              <span className="text-sm font-medium animate-pulse">Processing request...</span>
            </div>
          )}
          
          {content && (
            <div className="prose prose-invert max-w-none text-sm leading-relaxed">
              <ReactMarkdown
                components={{
                  code({node, inline, className, children, ...props}) {
                    const match = /language-(\w+)/.exec(className || '');
                    return !inline && match ? (
                      <div className="rounded-lg overflow-hidden my-4 border border-border/50 shadow-xl">
                        <SyntaxHighlighter
                          children={String(children).replace(/\n$/, '')}
                          style={atomDark}
                          language={match[1]}
                          PreTag="div"
                          customStyle={{ margin: 0, padding: '1rem', background: 'rgba(0,0,0,0.5)' }}
                          {...props}
                        />
                      </div>
                    ) : (
                      <code className="bg-white/10 text-indigo-300 rounded px-1.5 py-0.5 text-[0.9em]" {...props}>
                        {children}
                      </code>
                    )
                  }
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          )}

          {modality === 'image' && status === 'completed' && mediaUrl && (
            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2 }}
              className="mt-4 rounded-xl overflow-hidden border border-border/50 shadow-2xl relative group"
            >
              <img src={mediaUrl} alt="Generated" className="w-full h-auto object-cover max-h-[500px]" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
            </motion.div>
          )}

          {modality === 'voice' && status === 'completed' && mediaUrl && (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-4 p-4 rounded-xl bg-black/40 border border-border flex flex-col gap-2"
            >
              <div className="flex items-center gap-2 text-emerald-400 mb-2">
                <Music size={16} />
                <span className="text-xs font-semibold uppercase tracking-wider">Audio Generated</span>
              </div>
              <audio controls src={mediaUrl} className="w-full max-w-md h-10 outline-none"></audio>
            </motion.div>
          )}
          
          {status === 'failed' && (
            <div className="mt-3 p-3 rounded-lg bg-red-900/20 border border-red-500/30 text-red-400 text-sm">
              <p className="font-medium">{errorMessage || 'Failed to process request.'}</p>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
