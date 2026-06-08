/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        canvas: {
          DEFAULT: "#f4f4f5",
          dark: "#1c1c1f",
        },
        panel: {
          DEFAULT: "#ffffff",
          dark: "#28282d",
        },
        line: {
          DEFAULT: "#e4e4e7",
          dark: "#3a3a42",
        },
      },
    },
  },
  plugins: [],
};
