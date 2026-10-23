/** SearchSphere palette: navy, off-white, charcoal, muted gray, teal accent. */
module.exports = {
  content: ["./app/**/*.{js,jsx}", "./components/**/*.{js,jsx}", "./lib/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 50: "#eef2f7", 100: "#d9e1ec", 200: "#b3c3d8", 300: "#7f98ba", 400: "#4d6e97", 500: "#2d4a73", 600: "#1f3658", 700: "#182b47", 800: "#12223a", 900: "#0c172a" },
        paper: { DEFAULT: "#f7f6f2", dark: "#eceae3" },
        ink: { DEFAULT: "#232830", soft: "#3b424d" },
        mute: { DEFAULT: "#6b7380", light: "#9aa1ac", line: "#dcdad2" },
        teal: { 50: "#e8f5f3", 100: "#c7e7e2", 200: "#94cfc7", 500: "#14877c", 600: "#0f766e", 700: "#0d5f59", 800: "#0b4a46" },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Cascadia Mono", "Consolas", "Menlo", "monospace"],
      },
      borderRadius: { DEFAULT: "4px", md: "6px", lg: "8px" },
    },
  },
  plugins: [],
};
