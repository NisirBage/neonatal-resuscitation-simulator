/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        clinical: {
          ink: "#172026",
          panel: "#f7faf9",
          line: "#d7e2de",
          green: "#0f766e",
          blue: "#2563eb",
          rose: "#be123c"
        }
      },
      boxShadow: {
        soft: "0 12px 30px rgba(23, 32, 38, 0.08)"
      }
    }
  },
  plugins: []
};
