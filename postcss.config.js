/**
 * PostCSS configuration for PETio UI
 * Processes Tailwind CSS and applies Autoprefixer.
 */
module.exports = {
  plugins: [
    require('tailwindcss'),
    require('autoprefixer')
  ]
};