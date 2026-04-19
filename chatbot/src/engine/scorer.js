function priceScore(price) {
  if (price >= 300 && price <= 900) return 1.0
  if (price < 300) return 0.6
  return 0.7
}

export function scoreProducts(products, detectedScenarios) {
  return products
    .map(product => {
      const matchCount = detectedScenarios.filter(s => product.scenarios.includes(s)).length
      const scenarioScore = matchCount / detectedScenarios.length

      const total =
        scenarioScore * 0.5 +
        priceScore(product.price) * 0.2 +
        (product.popularity / 5) * 0.2 +
        (product.inStock ? 1 : 0) * 0.1

      return { ...product, _score: total }
    })
    .filter(p => p._score > 0)
    .sort((a, b) => b._score - a._score)
}
