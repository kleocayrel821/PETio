/**
 * Tailwind configuration for PETio UI
 * Includes DaisyUI plugin and scans Django templates and JS for class usage.
 */
module.exports = {
  content: [
    './templates/**/*.html',
    './controller/templates/**/*.html',
    './social/templates/**/*.html',
    './marketplace/templates/**/*.html',
    './accounts/templates/**/*.html',
    './static/js/**/*.js'
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#7C3AED',
          light: '#A78BFA',
          dark: '#5B21B6'
        }
      }
    }
  },
  plugins: [require('daisyui')],
  daisyui: {
    themes: ['light']
  }
};