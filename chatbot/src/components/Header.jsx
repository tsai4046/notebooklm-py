export default function Header() {
  return (
    <header className="bg-stone-800 text-cream-100 px-6 py-4 flex items-center gap-3 shadow-warm flex-shrink-0">
      <span className="text-2xl">🌿</span>
      <div>
        <h1 className="text-lg font-semibold tracking-wide text-amber-200">AromaSense AI</h1>
        <p className="text-xs text-stone-400">智慧香氛導購助理</p>
      </div>
      <div className="ml-auto flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span className="text-xs text-stone-400">線上服務中</span>
      </div>
    </header>
  )
}
