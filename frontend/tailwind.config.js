/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0a0a0f',
        panel: 'rgba(255, 255, 255, 0.03)',
        border: 'rgba(255, 255, 255, 0.06)',
      }
    },
  },
  plugins: [],
}
