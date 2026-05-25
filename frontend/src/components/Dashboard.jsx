import React, { useState, useEffect } from 'react';
import { ApiClient } from '../ApiClient';
import { Key, Activity, BarChart, AlertCircle, Copy, Check, Trash2, Plus, Clock } from 'lucide-react';
import { motion } from 'framer-motion';

export default function Dashboard() {
  const [usage, setUsage] = useState(null);
  const [apiKeys, setApiKeys] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState('');
  const [creatingKey, setCreatingKey] = useState(false);
  const [copiedKey, setCopiedKey] = useState(null);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [usageData, keysData] = await Promise.all([
        ApiClient.getUsage(30),
        ApiClient.getApiKeys()
      ]);
      setUsage(usageData);
      setApiKeys(keysData);
    } catch (err) {
      console.error("Failed to fetch dashboard data:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateKey = async (e) => {
    e.preventDefault();
    if (!newKeyName.trim()) return;
    setCreatingKey(true);
    try {
      const res = await ApiClient.createApiKey(newKeyName.trim());
      setNewlyCreatedKey(res.raw_key);
      setNewKeyName('');
      fetchData(); // Refresh list
    } catch (err) {
      console.error(err);
      alert("Failed to create key");
    } finally {
      setCreatingKey(false);
    }
  };

  const handleRevoke = async (keyId) => {
    if (!confirm("Are you sure you want to revoke this key? This cannot be undone.")) return;
    try {
      await ApiClient.revokeApiKey(keyId);
      fetchData(); // Refresh list
    } catch (err) {
      console.error(err);
      alert("Failed to revoke key");
    }
  };

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(text);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-pulse flex gap-2">
           <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>
           <div className="w-2 h-2 bg-indigo-500 rounded-full delay-75"></div>
           <div className="w-2 h-2 bg-indigo-500 rounded-full delay-150"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-8 max-w-6xl mx-auto w-full">
      
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
          <Activity className="text-indigo-400" />
          Platform Overview
        </h1>
        <p className="text-slate-400">View your API usage and manage authentication keys.</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-12">
        <div className="bg-panel border border-border p-6 rounded-2xl flex flex-col">
          <span className="text-slate-400 text-sm font-medium mb-1 flex items-center gap-2"><BarChart size={16}/> Total Requests</span>
          <span className="text-3xl font-bold text-white">{usage?.summary?.total_requests || 0}</span>
        </div>
        <div className="bg-panel border border-border p-6 rounded-2xl flex flex-col">
          <span className="text-slate-400 text-sm font-medium mb-1 flex items-center gap-2"><AlertCircle size={16}/> Error Rate</span>
          <span className="text-3xl font-bold text-rose-400">
            {usage?.summary?.total_requests > 0 
              ? ((usage.summary.total_errors / usage.summary.total_requests) * 100).toFixed(1) 
              : 0}%
          </span>
        </div>
        <div className="bg-panel border border-border p-6 rounded-2xl flex flex-col">
          <span className="text-slate-400 text-sm font-medium mb-1 flex items-center gap-2"><Clock size={16}/> Avg Latency</span>
          <span className="text-3xl font-bold text-emerald-400">
            {usage?.summary?.avg_latency_ms ? Math.round(usage.summary.avg_latency_ms) : 0}ms
          </span>
        </div>
        <div className="bg-panel border border-border p-6 rounded-2xl flex flex-col">
          <span className="text-slate-400 text-sm font-medium mb-1 flex items-center gap-2"><Key size={16}/> Active Keys</span>
          <span className="text-3xl font-bold text-white">{apiKeys.filter(k => k.is_active).length}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* API Keys Section */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Key className="text-purple-400" size={20} />
            API Keys
          </h2>
          
          <div className="bg-panel border border-border rounded-2xl overflow-hidden">
            <div className="p-4 border-b border-border bg-black/20">
              <form onSubmit={handleCreateKey} className="flex gap-2">
                <input 
                  type="text" 
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="New API Key Name" 
                  className="flex-1 bg-black/40 border border-border rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-indigo-500/50"
                  required
                />
                <button 
                  type="submit" 
                  disabled={creatingKey || !newKeyName.trim()}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl text-sm font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
                >
                  <Plus size={16} /> Create Key
                </button>
              </form>
            </div>

            {newlyCreatedKey && (
              <div className="p-4 bg-indigo-500/10 border-b border-indigo-500/20">
                <p className="text-sm text-indigo-300 font-medium mb-2">Save this key now. It will not be shown again.</p>
                <div className="flex items-center justify-between bg-black/40 px-4 py-3 rounded-xl border border-indigo-500/30">
                  <code className="text-indigo-200 font-mono text-sm">{newlyCreatedKey}</code>
                  <button 
                    onClick={() => handleCopy(newlyCreatedKey)}
                    className="text-slate-400 hover:text-white transition-colors p-1"
                  >
                    {copiedKey === newlyCreatedKey ? <Check size={18} className="text-emerald-400"/> : <Copy size={18} />}
                  </button>
                </div>
              </div>
            )}

            <div className="divide-y divide-border">
              {apiKeys.map(key => (
                <div key={key.id} className={`p-4 flex items-center justify-between ${!key.is_active ? 'opacity-50' : ''}`}>
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <span className="font-semibold text-slate-200">{key.name}</span>
                      {!key.is_active && <span className="text-[10px] uppercase tracking-wider bg-rose-500/20 text-rose-400 px-2 py-0.5 rounded-full font-bold">Revoked</span>}
                    </div>
                    <div className="text-xs text-slate-500 font-mono bg-black/30 px-2 py-1 rounded inline-block">
                      {key.masked_key}
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right hidden sm:block">
                      <div className="text-xs text-slate-400">Rate Limit</div>
                      <div className="text-sm font-medium text-slate-300">{key.rate_limit_rpm} RPM</div>
                    </div>
                    {key.is_active && (
                      <button 
                        onClick={() => handleRevoke(key.id)}
                        className="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-400/10 rounded-lg transition-colors"
                        title="Revoke Key"
                      >
                        <Trash2 size={18} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
              
              {apiKeys.length === 0 && (
                <div className="p-8 text-center text-slate-500 text-sm">
                  No API keys found.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Modality Breakdown */}
        <div className="flex flex-col gap-4">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <BarChart className="text-orange-400" size={20} />
            Usage by Modality
          </h2>
          <div className="bg-panel border border-border rounded-2xl p-4 flex flex-col gap-3">
            {Object.keys(usage?.by_modality || {}).length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">No usage data yet.</div>
            ) : (
              Object.entries(usage.by_modality).map(([mod, stats]) => (
                <div key={mod} className="flex flex-col gap-1.5 p-3 rounded-xl bg-black/20 border border-border/50">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-slate-200 capitalize">{mod.replace('_', ' ')}</span>
                    <span className="text-sm font-bold text-white">{stats.requests} reqs</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <span className="flex items-center gap-1"><Clock size={12}/> {Math.round(stats.avg_latency_ms)}ms</span>
                    <span>•</span>
                    <span className="flex items-center gap-1 text-rose-400"><AlertCircle size={12}/> {stats.errors} errs</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
