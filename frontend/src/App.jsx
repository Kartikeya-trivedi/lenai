import React, { useState, useRef, useEffect } from 'react';
import { ApiClient } from './ApiClient';
import MessageBubble from './components/MessageBubble';
import OmniInput from './components/OmniInput';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles } from 'lucide-react';

function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const feedRef = useRef(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTo({
        top: feedRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages]);

  const handleSubmit = async (text, modality) => {
    // 1. Add user message
    const userMsgId = Date.now().toString();
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: text, modality }]);

    // 2. Add empty processing assistant message
    const botMsgId = (Date.now() + 1).toString();
    setMessages(prev => [...prev, { 
      id: botMsgId, 
      role: 'assistant', 
      content: '', 
      modality,
      status: 'processing' 
    }]);

    setIsLoading(true);

    try {
      if (modality === 'text') {
        const response = await ApiClient.chat(text);
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { ...msg, content: response.answer, status: 'completed' } : msg
        ));
      } else if (modality === 'image') {
        const response = await ApiClient.generateImage(text);
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { 
            ...msg, 
            status: 'completed', 
            content: `Generated image for: "${text}"`,
            mediaUrl: response.output_url
          } : msg
        ));
      } else if (modality === 'voice') {
        const response = await ApiClient.generateVoice(text);
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { 
            ...msg, 
            status: 'completed', 
            content: `Generated voice for: "${text}"`,
            mediaUrl: response.output_url
          } : msg
        ));
      } else {
        // Fallback for video not fully implemented yet
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { 
            ...msg, 
            content: `The ${modality} modality is currently under construction. Please try Chat, Image, or Voice.`, 
            status: 'completed' 
          } : msg
        ));
      }
    } catch (error) {
      console.error(error);
      setMessages(prev => prev.map(msg => 
        msg.id === botMsgId ? { ...msg, status: 'failed' } : msg
      ));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-background relative overflow-hidden">
      {/* Background ambient lighting */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-600/10 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-0 right-1/4 w-[600px] h-[600px] bg-purple-600/10 rounded-full blur-[150px] pointer-events-none"></div>

      {/* Header */}
      <header className="h-16 flex-shrink-0 flex items-center px-6 border-b border-border/50 bg-background/50 backdrop-blur-xl z-20">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Sparkles size={16} className="text-white" />
          </div>
          <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400 tracking-tight">
            LenAI Omni
          </h1>
        </div>
        <div className="ml-auto flex items-center gap-3 glass-panel px-3 py-1.5 rounded-full">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse-slow shadow-[0_0_8px_rgba(16,185,129,0.8)]"></div>
          <span className="text-xs text-emerald-400 font-semibold tracking-widest uppercase">Systems Online</span>
        </div>
      </header>

      {/* Chat Feed */}
      <main 
        ref={feedRef}
        className="flex-1 overflow-y-auto p-4 md:p-8 flex flex-col gap-2 pb-40 z-10 scroll-smooth"
      >
        <div className="max-w-4xl w-full mx-auto relative min-h-full flex flex-col">
          {messages.length === 0 ? (
            <motion.div 
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, ease: "easeOut" }}
              className="flex-1 flex flex-col items-center justify-center text-center pb-48"
            >
              <div className="w-20 h-20 mb-6 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-600/20 border border-indigo-500/30 flex items-center justify-center shadow-[0_0_50px_rgba(99,102,241,0.15)]">
                <Sparkles size={40} className="text-indigo-400" />
              </div>
              <h2 className="text-4xl md:text-5xl font-bold mb-4 tracking-tight">
                Welcome to <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-400 to-emerald-400 animate-gradient-x">LenAI</span>
              </h2>
              <p className="text-slate-400 text-lg max-w-xl font-medium leading-relaxed">
                Experience the next generation of multimodal AI. Generate text, images, and voice all in one unified seamless interface.
              </p>
            </motion.div>
          ) : (
            <AnimatePresence initial={false}>
              {messages.map(msg => (
                <MessageBubble key={msg.id} {...msg} />
              ))}
              {/* Spacer to clear the absolute-positioned input area */}
              <div className="h-32 flex-shrink-0" />
            </AnimatePresence>
          )}
        </div>
      </main>

      {/* Input Area */}
      <div className="absolute bottom-0 left-0 right-0 p-4 md:p-6 bg-gradient-to-t from-background via-background/95 to-transparent pt-20 z-20">
        <OmniInput onSubmit={handleSubmit} isLoading={isLoading} />
      </div>
    </div>
  );
}

export default App;
