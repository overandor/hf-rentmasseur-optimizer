/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          deep: "#0a0a0f",
          panel: "#12121a",
          glass: "#1a1a2e",
        },
        accent: {
          orange: "#ff6b1a",
          dim: "#cc5515",
          glow: "#ff8c42",
        },
        signal: {
          live: "#00ff88",
          warn: "#ffaa00",
          crit: "#ff3344",
          verified: "#00aaff",
          dormant: "#555566",
        },
      },
      fontFamily: {
        mono: ["SF Mono", "Monaco", "Consolas", "monospace"],
      },
      animation: {
        pulse: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        glow: "glow 3s ease-in-out infinite",
        scan: "scan 4s linear infinite",
      },
      keyframes: {
        glow: {
          "0%, 100%": { boxShadow: "0 0 5px rgba(255,107,26,0.3)" },
          "50%": { boxShadow: "0 0 20px rgba(255,107,26,0.6)" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
      },
    },
  },
  plugins: [],
};
