/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#0D1B2A", 2: "#162234", 3: "#1D2E44", 4: "#243550" },
        steel: "#2C4B6E",
        mid: "#3A6898",
        accent: { DEFAULT: "#4A9DDA", 2: "#5BB8F5" },
        gold: { DEFAULT: "#F5A623", 2: "#FFB733" },
        permit: {
          green: "#27AE60",
          green2: "#2ECC71",
          red: "#E74C3C",
          red2: "#FF6B5B",
          orange: "#F39C12",
        },
        txt: { 1: "#EDF2F7", 2: "#A8BAD0", 3: "#6B8CAE" },
      },
      fontFamily: {
        sans: ["DM Sans", "sans-serif"],
        mono: ["DM Mono", "monospace"],
      },
      borderColor: {
        subtle: "rgba(255,255,255,0.07)",
        subtle2: "rgba(255,255,255,0.12)",
      },
    },
  },
  plugins: [],
};
