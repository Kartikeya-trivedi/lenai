import React, { useState, useRef, useEffect } from 'react';
import { ApiClient } from './ApiClient';
import MessageBubble from './components/MessageBubble';
import OmniInput from './components/OmniInput';

function App() {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: "Welcome to LenAI Omni. I can chat with you, generate images, convert text-to-speech, or animate videos. How can I help you today?",
      status: 'completed'
    }
  ]);
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
            mediaUrl: `data:image/png;base64,${response.result.images[0]}`
          } : msg
        ));
      } else {
        // Fallback for voice/video not fully implemented yet
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { 
            ...msg, 
            content: `The ${modality} modality is currently under construction. Please try 'Chat' or 'Image'.`, 
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
      {/* Header */}
      <header className="h-16 flex-shrink-0 flex items-center px-6 border-b border-border bg-black/20 backdrop-blur-md z-10">
        <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400">
          LenAI Omni
        </h1>
        <div className="ml-auto flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
          <span className="text-xs text-emerald-400 font-medium tracking-wide uppercase">Systems Online</span>
        </div>
      </header>

      {/* Chat Feed */}
      <main 
        ref={feedRef}
        className="flex-1 overflow-y-auto p-4 md:p-8 flex flex-col gap-2 pb-32"
      >
        <div className="max-w-4xl w-full mx-auto">
          {messages.map(msg => (
            <MessageBubble key={msg.id} {...msg} />
          ))}
        </div>
      </main>

      {/* Input Area */}
      <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-background via-background to-transparent pt-12 z-10">
        <OmniInput onSubmit={handleSubmit} isLoading={isLoading} />
      </div>
    </div>
  );
}

export default App;
