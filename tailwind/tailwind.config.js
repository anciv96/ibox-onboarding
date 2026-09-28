module.exports = {
  darkMode: 'class',
  content: ['../templates/**/*.html', '../*/templates/**/*.html', '../static/js/*.js', '../*/*.py'],
  theme: { extend: { colors: { brand: {
    50: '#eff4ff', 100: '#dbe6fe', 200: '#bfd3fe', 300: '#93b6fd', 400: '#5f8ffa',
    500: '#3b6ff5', 600: '#2663eb', 700: '#1d4fc9', 800: '#1c43a3', 900: '#1c3b81' } } } },
  plugins: [require('@tailwindcss/typography')],
};
