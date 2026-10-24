/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          900: "#0b2138",
          800: "#0f2a43",
          700: "#16395c",
          600: "#1d4a77",
          100: "#e2edf7",
          50: "#f3f8fc",
        },
        teal: {
          600: "#0d9488",
          500: "#14b8a6",
          100: "#ccfbf1",
        },
        risk: {
          none: "#16a34a",
          noneBg: "#dcfce7",
          medium: "#d97706",
          mediumBg: "#fef3c7",
          high: "#ea580c",
          highBg: "#ffedd5",
          critical: "#dc2626",
          criticalBg: "#fee2e2",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};