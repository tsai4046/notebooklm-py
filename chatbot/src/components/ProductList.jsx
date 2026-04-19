import ProductCard from './ProductCard.jsx'

export default function ProductList({ products }) {
  if (!products || products.length === 0) return null

  return (
    <div className="px-4 py-3 bg-cream-50 border-t border-stone-100">
      <p className="text-xs text-ink-light mb-3 font-medium uppercase tracking-wide">為您推薦的商品</p>
      <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide">
        {products.map(p => (
          <ProductCard key={p.id} product={p} />
        ))}
      </div>
    </div>
  )
}
