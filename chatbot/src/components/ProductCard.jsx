const SCENARIO_LABELS = {
  relax: '放鬆',
  sleep: '助眠',
  focus: '專注',
  nature: '大自然',
  fresh: '清新',
  gift: '送禮',
}

function PopularityDots({ value }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={`w-1.5 h-1.5 rounded-full ${i < value ? 'bg-gold-500' : 'bg-stone-200'}`} />
      ))}
    </div>
  )
}

export default function ProductCard({ product }) {
  return (
    <div className="bg-white rounded-2xl shadow-card hover:shadow-warm transition-shadow duration-200 overflow-hidden min-w-[220px] max-w-[240px] flex-shrink-0">
      <div className="bg-rose-100 px-4 py-5 flex items-center justify-between">
        <span className="text-4xl">{product.emoji}</span>
        <span className="text-xs text-rose-600 bg-white px-2 py-0.5 rounded-full font-medium">
          {product.category}
        </span>
      </div>
      <div className="p-4 flex flex-col gap-2">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink leading-tight">{product.name}</h3>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-gold-600 font-semibold text-sm">NT${product.price.toLocaleString()}</span>
          <PopularityDots value={product.popularity} />
        </div>
        <p className="text-xs text-ink-soft leading-relaxed">{product.description}</p>
        <div className="flex flex-wrap gap-1 mt-1">
          {product.scentNotes.map(note => (
            <span key={note} className="text-xs bg-cream-200 text-ink-soft px-2 py-0.5 rounded-full">
              {note}
            </span>
          ))}
        </div>
        <div className="flex flex-wrap gap-1">
          {product.scenarios.map(s => (
            <span key={s} className="text-xs bg-rose-100 text-rose-600 px-2 py-0.5 rounded-full font-medium">
              {SCENARIO_LABELS[s] || s}
            </span>
          ))}
        </div>
        {!product.inStock && (
          <span className="text-xs text-stone-400 text-center">暫時缺貨</span>
        )}
        <button
          className={`mt-2 w-full py-2 rounded-xl text-sm font-medium transition-colors duration-150
            ${product.inStock
              ? 'bg-rose-600 hover:bg-rose-800 text-white'
              : 'bg-stone-100 text-stone-400 cursor-not-allowed'
            }`}
          disabled={!product.inStock}
          onClick={() => alert(`已加入購物車：${product.name}`)}
        >
          {product.inStock ? '查看商品' : '補貨中'}
        </button>
      </div>
    </div>
  )
}
