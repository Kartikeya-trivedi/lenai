import React, { useState, useRef, useEffect } from 'react';
import { ApiClient, clearApiKey, getActiveApiKey, saveApiKey } from './ApiClient';
import MessageBubble from './components/MessageBubble';
import OmniInput from './components/OmniInput';
import Dashboard from './components/Dashboard';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Key, Terminal, LayoutDashboard } from 'lucide-react';

function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [apiKey, setApiKey] = useState(() => getActiveApiKey());
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState(() => !!getActiveApiKey());
  const [isConnecting, setIsConnecting] = useState(false);
  const [authError, setAuthError] = useState('');
  const [activeTab, setActiveTab] = useState('playground'); // 'playground' | 'dashboard'
  const feedRef = useRef(null);

  const handleSignOut = () => {
    clearApiKey();
    setApiKey('');
    setAuthError('');
    setIsAuthenticated(false);
  };

  useEffect(() => {
    const key = getActiveApiKey();
    if (!key) {
      setIsCheckingAuth(false);
      return;
    }

    let cancelled = false;

    ApiClient.validateApiKey(key)
      .then(() => {
        if (!cancelled) {
          setIsAuthenticated(true);
          setAuthError('');
        }
      })
      .catch(() => {
        clearApiKey();
        if (!cancelled) {
          setApiKey('');
          setIsAuthenticated(false);
          setAuthError('Saved API key is invalid or expired. Enter a valid key to continue.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsCheckingAuth(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTo({
        top: feedRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages]);

  const handleConnect = async (e) => {
    e.preventDefault();

    const candidate = apiKey.trim();
    if (!candidate) return;

    setIsConnecting(true);
    setAuthError('');

    try {
      await ApiClient.validateApiKey(candidate);
      saveApiKey(candidate);
      setIsAuthenticated(true);
    } catch (error) {
      clearApiKey();
      const status = error?.response?.status;
      const detail = error?.response?.data?.error?.message || error?.response?.data?.detail;
      setAuthError(
        status === 401
          ? 'Invalid API key. Check the key and try again.'
          : detail || 'Could not validate this API key. Try again in a moment.'
      );
    } finally {
      setIsConnecting(false);
    }
  };

  if (isCheckingAuth) {
    return (
      <div className="flex flex-col h-screen bg-background items-center justify-center p-4">
        <div className="flex items-center gap-3 text-slate-300 text-sm">
          <Sparkles size={18} className="text-indigo-400 animate-pulse" />
          Checking API key...
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col h-screen bg-background items-center justify-center p-4">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="max-w-md w-full bg-panel p-8 rounded-3xl border border-border shadow-2xl flex flex-col items-center text-center"
        >
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-600/20 border border-indigo-500/30 flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(99,102,241,0.15)]">
            <Sparkles size={32} className="text-indigo-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Welcome to LenAI</h2>
          <p className="text-slate-400 text-sm mb-8">Enter your API key to access the media inference platform.</p>
          
          <form 
            onSubmit={handleConnect}
            className="w-full"
          >
            <input 
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="lenai_sk_..."
              className="w-full bg-[#1e1e1e] border border-border rounded-xl px-4 py-3 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 mb-4 transition-colors"
              autoFocus
            />
            {authError && (
              <p className="text-sm text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-xl px-3 py-2 mb-4 text-left">
                {authError}
              </p>
            )}
            <button 
              type="submit"
              disabled={!apiKey.trim() || isConnecting}
              className="w-full bg-white text-black font-semibold rounded-xl py-3 hover:bg-slate-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Key size={16} />
              {isConnecting ? 'Checking...' : 'Connect'}
            </button>
          </form>
        </motion.div>
      </div>
    );
  }

  const handleTranscribeAudio = async (file) => {
    const response = await ApiClient.transcribeAudio(file);
    return response.transcript || '';
  };

  const handleFileUpload = async (file, isAudio = false) => {
    if (!file) return;

    const botMsgId = Date.now().toString() + "_upload";
    
    if (isAudio) {
      setMessages(prev => [...prev, { 
        id: botMsgId, 
        role: 'assistant', 
        content: `Transcribing audio file: **${file.name}**...`, 
        modality: 'chat',
        status: 'processing' 
      }]);

      try {
        const response = await ApiClient.transcribeAudio(file);
        const transcript = response.transcript || 'No transcript text was returned.';
        
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { 
            ...msg, 
            content: transcript, 
            status: 'completed' 
          } : msg
        ));
      } catch (err) {
        console.error(err);
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { ...msg, content: `Failed to transcribe audio: ${err.message}`, status: 'failed' } : msg
        ));
      }
    } else {
      setMessages(prev => [...prev, { 
        id: botMsgId, 
        role: 'assistant', 
        content: `Uploading document: **${file.name}**...`, 
        modality: 'chat',
        status: 'processing' 
      }]);

      try {
        const text = await file.text();
        const res = await ApiClient.ingestDocument(text, file.name);
        
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { ...msg, content: `Successfully ingested document: **${file.name}** (${res.chunks} chunks embedded and stored in Qdrant!)`, status: 'completed' } : msg
        ));
      } catch (err) {
        console.error(err);
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { ...msg, content: `Failed to upload document: ${err.message}`, status: 'failed' } : msg
        ));
      }
    }
  };

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
      if (modality === 'text' || modality === 'chat' || modality === 'search') {
        // If web search or deep research, could pass specific flags. For now, text handles it.
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
        setMessages(prev => prev.map(msg => 
          msg.id === botMsgId ? { 
            ...msg, 
            content: `The ${modality} modality is currently under construction.`, 
            status: 'completed' 
          } : msg
        ));
      }
    } catch (error) {
      console.error(error);
      let errorMsg = error?.message || 'Unknown error';
      if (error?.response?.status === 401) {
        clearApiKey();
        setApiKey('');
        setIsAuthenticated(false);
        setAuthError('Authentication failed. Enter a valid API key to continue.');
        errorMsg = 'Authentication failed - invalid or missing API key. Please sign out and re-enter a valid key.';
      } else if (error?.response?.data?.detail) {
        errorMsg = error.response.data.detail;
      }
      setMessages(prev => prev.map(msg =>
        msg.id === botMsgId ? { ...msg, status: 'failed', errorMessage: errorMsg } : msg
      ));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col bg-background font-sans overflow-hidden md:flex-row">
      {/* Mobile Navigation */}
      <header className="flex-shrink-0 border-b border-border bg-panel/95 px-3 pb-3 pt-3 md:hidden">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-indigo-500/30 bg-indigo-500/20">
              <Sparkles size={18} className="text-indigo-400" />
            </div>
            <span className="truncate text-lg font-bold tracking-wide text-white">LenAI</span>
          </div>
          <button
            onClick={handleSignOut}
            className="flex-shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-rose-400 hover:bg-rose-400/10 hover:text-rose-300"
          >
            Sign Out
          </button>
        </div>

        <nav className="grid grid-cols-2 gap-2">
          <button
            onClick={() => setActiveTab('playground')}
            className={`flex min-h-11 items-center justify-center gap-2 rounded-xl px-3 text-sm font-medium transition-colors ${activeTab === 'playground' ? 'bg-white/10 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'}`}
          >
            <Terminal size={17} /> Playground
          </button>
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`flex min-h-11 items-center justify-center gap-2 rounded-xl px-3 text-sm font-medium transition-colors ${activeTab === 'dashboard' ? 'bg-white/10 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'}`}
          >
            <LayoutDashboard size={17} /> Dashboard
          </button>
        </nav>
      </header>
      
      {/* Sidebar Navigation */}
      <div className="hidden w-64 flex-shrink-0 border-r border-border bg-panel p-4 md:flex md:flex-col">
        <div className="flex items-center gap-3 mb-8 px-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
            <Sparkles size={18} className="text-indigo-400" />
          </div>
          <span className="font-bold text-white text-lg tracking-wide">LenAI</span>
        </div>
        
        <nav className="flex flex-col gap-2">
          <button 
            onClick={() => setActiveTab('playground')}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors ${activeTab === 'playground' ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}
          >
            <Terminal size={18} /> Playground
          </button>
          <button 
            onClick={() => setActiveTab('dashboard')}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors ${activeTab === 'dashboard' ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}`}
          >
            <LayoutDashboard size={18} /> Dashboard
          </button>
        </nav>

        <div className="mt-auto pt-4 border-t border-border px-2">
          <button 
            onClick={handleSignOut}
            className="flex items-center gap-2 text-xs text-rose-400 hover:text-rose-300 font-medium"
          >
            Sign Out
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {activeTab === 'dashboard' ? (
        <Dashboard />
      ) : (
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col items-center overflow-hidden">
          <AnimatePresence>
            {messages.length === 0 ? (
              <motion.div 
                key="empty"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20, filter: 'blur(10px)' }}
                className="flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-4 pb-8 pt-6 sm:px-6 md:pb-32"
              >
                <h1 className="mb-6 text-center text-2xl font-semibold tracking-tight text-slate-100 sm:mb-8 sm:text-[32px]">
                  What are you working on?
                </h1>
                
                <div className="w-full relative z-10">
                  <OmniInput
                    onSubmit={handleSubmit}
                    onFileUpload={handleFileUpload}
                    onTranscribeAudio={handleTranscribeAudio}
                    isLoading={isLoading}
                    centered={true}
                  />
                </div>
              </motion.div>
            ) : (
              <motion.div 
                key="chat"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex w-full min-h-0 flex-1 flex-col items-center overflow-hidden"
              >
                {/* Chat Feed */}
                <div 
                  ref={feedRef}
                  className="w-full flex-1 overflow-y-auto scroll-smooth px-3 py-4 sm:px-4 sm:py-8"
                >
                  <div className="mx-auto flex max-w-3xl flex-col gap-4 sm:gap-6">
                    {messages.map(msg => (
                      <MessageBubble key={msg.id} {...msg} />
                    ))}
                  </div>
                </div>

                {/* Bottom Input Area */}
                <div className="relative z-10 w-full max-w-3xl bg-gradient-to-t from-background via-background to-transparent px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-2 sm:px-6 sm:pb-6">
                  <OmniInput
                    onSubmit={handleSubmit}
                    onFileUpload={handleFileUpload}
                    onTranscribeAudio={handleTranscribeAudio}
                    isLoading={isLoading}
                    centered={false}
                  />
                  <div className="text-center mt-3 text-[11px] text-slate-500 font-medium">
                    LenAI can generate images, voice, and text.
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

export default App;
