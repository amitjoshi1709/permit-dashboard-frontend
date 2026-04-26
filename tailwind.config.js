/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Backgrounds — bone is the page, white is cards
        bone: {
          DEFAULT: "#EDE7DB",
          50: "#FFFFFF",
          200: "#DDD4C2",
        },
        stone: {
          100: "#E3D9C6",
        },
        // Inks — high-contrast warm charcoal
        ink: {
          DEFAULT: "#111315",
          700: "#1E2228",
          500: "#3D454D",
          400: "#5A636C",
        },
        // Steel navy
        steel: {
          DEFAULT: "#1F3A52",
          900: "#0E1E30",
          800: "#152B42",
          600: "#2D517A",
        },
        // Amber — primary accent
        amber: {
          DEFAULT: "#B5631F",
          600: "#924E16",
          500: "#C87A2E",
          400: "#D9923F",
        },
        // Status
        status: {
          success: "#2E6A3B",
          error:   "#8B3025",
          warning: "#B5631F",
        },
      },
      fontFamily: {
        sans:  ["Inter", "system-ui", "sans-serif"],
        serif: ["Merriweather", "Georgia", "serif"],
      },
      letterSpacing: {
        eyebrow: "0.22em",
        btn:     "0.06em",
      },
      boxShadow: {
        card: "0 18px 40px -24px rgba(28, 31, 36, 0.18)",
      },
      borderRadius: {
        sm: "2px",
      },
    },
  },
  plugins: [],
};
