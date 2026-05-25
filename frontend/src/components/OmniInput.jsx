import React, { useState, useRef, useEffect } from 'react';
import { 
  Send, 
  Image as ImageIcon, 
  Mic, 
  Plus, 
  Paperclip,
  FileText,
  AudioLines,
  Loader2
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function OmniInput({ onSubmit, onFileUpload, onTranscribeAudio, isLoading, centered }) {
  const [text, setText] = useState('');
  const [modality, setModality] = useState('text'); // text, image, voice
  const [menuOpen, setMenuOpen] = useState(false);
  const [micMenuOpen, setMicMenuOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  
  const fileInputRef = useRef(null);
  const audioInputRef = useRef(null);
  const textareaRef = useRef(null);
  const menuRef = useRef(null);
  const micMenuRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
      if (micMenuRef.current && !micMenuRef.current.contains(event.target)) {
        setMicMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    if (!text.trim() || isLoading || isTranscribing) return;
    onSubmit(text, modality);
    setText('');
    setModality('text');
  };

  const handleFileChange = (e, isAudio = false) => {
    const file = e.target.files[0];
    if (file && isAudio) {
      transcribeIntoPrompt(file);
    } else if (file && onFileUpload) {
      onFileUpload(file, isAudio);
    }
    setMenuOpen(false);
    setMicMenuOpen(false);
    e.target.value = null;
  };

  const handleActionClick = (mode) => {
    setModality(mode);
    setMenuOpen(false);
  };

  const transcribeIntoPrompt = async (file) => {
    if (!file || !onTranscribeAudio || isTranscribing) return;

    setIsTranscribing(true);
    setModality('text');

    try {
      const transcript = (await onTranscribeAudio(file))?.trim();
      if (!transcript) {
        alert("I couldn't hear anything clearly.");
        return;
      }

      setText(prev => {
        const current = prev.trim();
        return current ? `${current} ${transcript}` : transcript;
      });
      setTimeout(() => textareaRef.current?.focus(), 0);
    } catch (err) {
      console.error("Error transcribing audio:", err);
      alert("Audio transcription failed.");
    } finally {
      setIsTranscribing(false);
    }
  };

  const startRecording = async () => {
    if (isTranscribing || isLoading) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const audioFile = new File([audioBlob], 'live_recording.webm', { type: 'audio/webm' });
        
        stream.getTracks().forEach(track => track.stop());
        
        setIsRecording(false);
        transcribeIntoPrompt(audioFile);
      };

      mediaRecorder.start();
      setIsRecording(true);
      setMicMenuOpen(false);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      alert("Microphone access denied or not available.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
    }
  };

  const getPlaceholder = () => {
    if (isTranscribing) return 'Transcribing audio...';
    if (isRecording) return 'Recording... Click the red stop button when finished.';
    switch (modality) {
      case 'image': return 'Describe the image you want to generate...';
      case 'voice': return 'Type the text you want spoken...';
      default: return 'Ask anything';
    }
  };

  const renderBadge = () => {
    if (modality === 'text') return null;
    
    let Icon = FileText;
    let label = '';
    let colorClass = '';

    if (modality === 'image') {
      Icon = ImageIcon; label = 'Image'; colorClass = 'text-purple-400';
    } else if (modality === 'voice') {
      Icon = Mic; label = 'Voice'; colorClass = 'text-emerald-400';
    }

    return (
      <motion.div 
        initial={{ opacity: 0, scale: 0.9, x: -10 }}
        animate={{ opacity: 1, scale: 1, x: 0 }}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-panel-hover border border-border cursor-pointer hover:bg-white/10 transition-colors"
        onClick={() => setModality('text')}
        title="Click to clear modality"
      >
        <Icon size={14} className={colorClass} />
        <span className={`text-xs font-semibold ${colorClass}`}>{label}</span>
      </motion.div>
    );
  };

  return (
    <div className="w-full flex flex-col gap-3 relative">
      <form 
        onSubmit={handleSubmit} 
        className="w-full bg-panel rounded-[26px] p-3 flex flex-col shadow-sm border border-border transition-all focus-within:ring-1 focus-within:ring-white/20"
      >
        {/* Top area: Textarea */}
        <textarea
          ref={textareaRef}
          disabled={isRecording || isTranscribing}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={getPlaceholder()}
          className="w-full bg-transparent text-slate-100 placeholder-slate-400 px-3 py-2 mb-2 min-h-[52px] max-h-[200px] resize-none focus:outline-none text-base font-medium leading-relaxed disabled:opacity-50"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
        />

        {/* Bottom area: Toolbar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 relative">
            
            {/* Menu Dropdown Container */}
            <div className="relative" ref={menuRef}>
               <button 
                  type="button"
                  onClick={() => setMenuOpen(!menuOpen)}
                  className="w-9 h-9 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-200 hover:bg-panel-hover transition-colors flex-shrink-0"
                >
                  <Plus size={22} className={`transition-transform duration-300 ${menuOpen ? 'rotate-45' : ''}`} />
               </button>

               {/* Popup Menu */}
               <AnimatePresence>
                  {menuOpen && (
                    <motion.div 
                      initial={{ opacity: 0, y: 10, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 10, scale: 0.95 }}
                      transition={{ duration: 0.15 }}
                      className="absolute bottom-12 left-0 w-56 bg-menu-bg border border-border rounded-2xl shadow-xl overflow-hidden z-50 flex flex-col py-2"
                    >
                      <button type="button" onClick={() => fileInputRef.current?.click()} className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5 transition-colors text-left">
                        <Paperclip size={18} className="text-slate-400" /> Add document
                      </button>
                      
                      <div className="h-px bg-border my-1 mx-3" />
                      
                      <button type="button" onClick={() => handleActionClick('image')} className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5 transition-colors text-left">
                        <ImageIcon size={18} className="text-slate-400" /> Create image
                      </button>
                      <button type="button" onClick={() => handleActionClick('voice')} className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5 transition-colors text-left">
                        <Mic size={18} className="text-slate-400" /> Generate voice
                      </button>
                    </motion.div>
                  )}
               </AnimatePresence>
            </div>

            {/* Selected Modality Badge */}
            {renderBadge()}

            {/* Hidden File Inputs */}
            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={(e) => handleFileChange(e, false)} 
              accept=".txt,.md,.csv,.pdf"
              className="hidden" 
            />
            <input 
              type="file" 
              ref={audioInputRef} 
              onChange={(e) => handleFileChange(e, true)} 
              accept="audio/*"
              className="hidden" 
            />
          </div>

          <div className="flex items-center gap-1">
             <div className="relative" ref={micMenuRef}>
               <button 
                 type="button" 
                 onClick={() => setMicMenuOpen(!micMenuOpen)}
                 disabled={isTranscribing}
                 className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed ${micMenuOpen || modality === 'voice' || isRecording || isTranscribing ? 'bg-white text-black' : 'text-slate-400 hover:text-slate-200 hover:bg-panel-hover'}`}
               >
                 {isTranscribing ? <Loader2 size={18} className="animate-spin" /> : <Mic size={18} />}
               </button>
               
               <AnimatePresence>
                  {micMenuOpen && (
                    <motion.div 
                      initial={{ opacity: 0, y: 10, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 10, scale: 0.95 }}
                      transition={{ duration: 0.15 }}
                      className="absolute bottom-12 right-0 w-48 bg-menu-bg border border-border rounded-2xl shadow-xl overflow-hidden z-50 flex flex-col py-2"
                    >
                      <button type="button" onClick={() => { setMicMenuOpen(false); handleActionClick('voice'); }} className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5 transition-colors text-left">
                        <Mic size={18} className="text-slate-400" /> Generate Voice
                      </button>
                      <button type="button" onClick={startRecording} className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5 transition-colors text-left">
                        <Mic size={18} className="text-rose-400" /> Dictate prompt
                      </button>
                      <button type="button" onClick={() => { setMicMenuOpen(false); audioInputRef.current?.click(); }} className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5 transition-colors text-left">
                        <AudioLines size={18} className="text-slate-400" /> Upload audio prompt
                      </button>
                    </motion.div>
                  )}
               </AnimatePresence>
             </div>
             
             {/* Submit button */}
             {isRecording ? (
               <button 
                 type="button"
                 onClick={stopRecording}
                 className="w-9 h-9 rounded-full flex items-center justify-center bg-rose-500 text-white hover:bg-rose-600 transition-colors flex-shrink-0 animate-pulse"
                 title="Stop Recording"
               >
                 <div className="w-3 h-3 bg-white rounded-sm"></div>
               </button>
             ) : text.trim() && !isLoading && !isTranscribing ? (
               <button 
                 type="submit"
                 className="w-9 h-9 rounded-full flex items-center justify-center bg-white text-black hover:bg-slate-200 transition-colors flex-shrink-0"
               >
                 <Send size={16} className="ml-0.5" />
               </button>
             ) : (
               <div className="w-9 h-9 rounded-full flex items-center justify-center text-slate-400 flex-shrink-0 bg-white text-black">
                 <div className="flex gap-1">
                   <div className="w-1 h-1.5 bg-black rounded-full animate-pulse"></div>
                   <div className="w-1 h-2 bg-black rounded-full animate-pulse delay-75"></div>
                   <div className="w-1 h-1 bg-black rounded-full animate-pulse delay-150"></div>
                 </div>
               </div>
             )}
          </div>
        </div>
      </form>

      {/* Action Chips */}
      {centered && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="flex flex-wrap items-center justify-center gap-3 mt-1"
        >
          <button 
            onClick={() => handleActionClick('image')}
            className="flex items-center gap-2 px-4 py-2 rounded-full border border-border hover:bg-panel transition-colors text-sm font-medium text-slate-300"
          >
            <ImageIcon size={15} className="text-purple-400" /> Create image
          </button>
          <button 
            onClick={() => handleActionClick('voice')}
            className="flex items-center gap-2 px-4 py-2 rounded-full border border-border hover:bg-panel transition-colors text-sm font-medium text-slate-300"
          >
            <Mic size={15} className="text-emerald-400" /> Generate voice
          </button>
        </motion.div>
      )}
    </div>
  );
}
