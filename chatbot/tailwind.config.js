/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        cream: {
          DEFAULT: '#FAF6F1',
          50: '#FDFAF7',
          100: '#FAF6F1',
          200: '#F2EAE0',
        },
        rose: {
          100: '#F4E4DC',
          200: '#E8C9BB',
          400: '#C9896F',
          600: '#A0614A',
          800: '#6B3828',
        },
        gold: {
          300: '#E8D5A3',
          400: '#D4B86A',
          500: '#B8963E',
          600: '#8C6F28',
        },
        ink: {
          DEFAULT: '#2C2420',
          soft: '#5C504A',
          light: '#9C8E87',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        serif: ['Georgia', 'serif'],
      },
      boxShadow: {
        card: '0 2px 12px rgba(44,36,32,0.08)',
        warm: '0 4px 24px rgba(160,97,74,0.15)',
      },
    },
  },
  plugins: [],
}
