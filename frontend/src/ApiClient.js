import axios from 'axios';

// Get API URL from env, default to local if running in dev without .env
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://mindrix--lenai-platform-api-gateway.modal.run';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// Guarantee headers are injected on every request
api.interceptors.request.use(config => {
  config.headers['X-API-Key'] = 'lenai_sk_dummy';
  config.headers['Content-Type'] = 'application/json';
  return config;
});

export const ApiClient = {
  async chat(prompt) {
    const res = await api.post('/v1/rag/query', { question: prompt });
    return res.data;
  },

  async generateImage(prompt) {
    // 1. Submit the job
    const res = await api.post('/v1/infer/image', {
      prompt,
      negative_prompt: 'blurry, low quality',
      width: 512,
      height: 512,
      steps: 20
    });
    
    const jobId = res.data.job_id;
    
    // 2. Poll until completed
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
            setTimeout(poll, 1500); // poll every 1.5s
          }
        } catch (err) {
          reject(err);
        }
      };
      setTimeout(poll, 1000); // initial delay 1s
    });
  }
};
