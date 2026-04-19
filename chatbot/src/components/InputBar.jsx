import { useState } from 'react'

export default function InputBar({ onSend, disabled }) {
  const [value, setValue] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const text = value.trim()
    if (!text || disabled) return
    onSend(text)
    setValue('')
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-3 px-4 py-3 bg-white border-t border-stone-200 flex-shrink-0"
    >
      <input
        type="text"
        value={value}
        onChange={e => setValue(e.target.value)}
        disabled={disabled}
        placeholder={disabled ? '正在回覆中…' : '輸入您的需求，例如：我想放鬆一下…'}
        className="flex-1 px-4 py-2.5 rounded-full bg-cream-100 border border-stone-200
                   text-sm text-ink placeholder:text-ink-light
                   focus:outline-none focus:border-rose-300 focus:ring-2 focus:ring-rose-100
                   disabled:opacity-60 transition-all"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        aria-label="送出訊息"
        className="w-10 h-10 rounded-full bg-rose-600 text-white flex items-center justify-center flex-shrink-0
                   hover:bg-rose-700 active:scale-95 transition-all duration-150
                   disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
          <path d="M3.105 2.288a.75.75 0 00-.826.95l1.903 6.84H10.5a.75.75 0 010 1.5H4.182l-1.903 6.84a.75.75 0 00.826.95 28.895 28.895 0 0015.863-7.493.75.75 0 000-1.134A28.894 28.894 0 003.105 2.288z" />
        </svg>
      </button>
    </form>
  )
}
