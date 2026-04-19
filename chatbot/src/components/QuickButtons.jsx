const QUICK_OPTIONS = [
  { key: 'relax',  label: '放鬆 Relax',   emoji: '😌' },
  { key: 'sleep',  label: '助眠 Sleep',   emoji: '🌙' },
  { key: 'focus',  label: '專注 Focus',   emoji: '🧘' },
  { key: 'nature', label: '森林感 Nature', emoji: '🌲' },
  { key: 'fresh',  label: '清新 Fresh',   emoji: '🍃' },
  { key: 'gift',   label: '送禮 Gift',    emoji: '🎁' },
]

export default function QuickButtons({ onQuickSelect }) {
  return (
    <div className="px-4 py-3 bg-cream-100 border-t border-stone-100 flex-shrink-0">
      <p className="text-xs text-ink-light mb-2">快速選擇需求</p>
      <div className="flex flex-wrap gap-2">
        {QUICK_OPTIONS.map(({ key, label, emoji }) => (
          <button
            key={key}
            onClick={() => onQuickSelect(key)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                       bg-white border border-stone-200 text-stone-600
                       hover:bg-rose-100 hover:border-rose-300 hover:text-rose-700
                       active:scale-95 transition-all duration-150"
          >
            <span>{emoji}</span>
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
