import axios from 'axios';

// Get API URL from env, default to local if running in dev without .env
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://mindrix--lenai-platform-api-gateway.modal.run';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// Guarantee headers are injected on every request
api.interceptors.request.use(config => {
  config.headers['X-API-Key'] = 'lenai_sk_dummy';
  return config;
});

export const ApiClient = {
  async chat(prompt) {
    const res = await api.post('/v1/rag/query', { question: prompt });
    return res.data;
  },

  async generateImage(prompt) {
    const formData = new FormData();
    formData.append('prompt', prompt);
    formData.append('negative_prompt', 'blurry, low quality');
    formData.append('width', 512);
    formData.append('height', 512);
    formData.append('steps', 20);

    const res = await api.post('/v1/infer/image', formData);
    return this.pollJob(res.data.job_id);
  },

  async generateVoice(text) {
    const formData = new FormData();
    formData.append('text', text);
    formData.append('voice', 'af_bella');
    formData.append('speed', 1.0);

    const res = await api.post('/v1/infer/voice_tts', formData);
    return this.pollJob(res.data.job_id);
  },

  async pollJob(jobId) {
    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          const statusRes = await api.get(`/v1/jobs/${jobId}`);
          const status = statusRes.data.status;
          
          if (status === 'completed') {
            resolve(statusRes.data);
          } else if (status === 'failed' || status === 'dead_letter') {
            reject(new Error(statusRes.data.error_message || 'Job failed'));
          } else {
            setTimeout(poll, 1500);
          }
        } catch (err) {
          reject(err);
        }
      };
      setTimeout(poll, 1000);
    });
  }
};
