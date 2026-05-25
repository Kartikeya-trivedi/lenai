/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0D0D0D', // Very dark near-black
        panel: '#2F2F2F', // Dark gray pill color
        'panel-hover': '#3A3A3A',
        border: 'rgba(255, 255, 255, 0.1)',
        'menu-bg': '#252526', // Dropdown menu background
      }
    },
  },
  plugins: [],
}
