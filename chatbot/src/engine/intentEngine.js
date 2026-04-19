import faqData from '../data/faq.json'
import productsData from '../data/products.json'
import { KEYWORD_MAP } from './keywords.js'
import { scoreProducts } from './scorer.js'

export function detect(userText) {
  const normalized = userText.toLowerCase().trim()

  // Step 1: FAQ check
  for (const faq of faqData) {
    for (const pattern of faq.patterns) {
      if (normalized.includes(pattern.toLowerCase())) {
        return { type: 'faq', payload: { answer: faq.answer, question: faq.question } }
      }
    }
  }

  // Step 2: Recommendation check
  const detectedScenarios = []
  for (const [scenarioKey, keywords] of Object.entries(KEYWORD_MAP)) {
    for (const keyword of keywords) {
      if (normalized.includes(keyword.toLowerCase())) {
        detectedScenarios.push(scenarioKey)
        break
      }
    }
  }

  if (detectedScenarios.length > 0) {
    const scored = scoreProducts(productsData, detectedScenarios)
    return {
      type: 'recommend',
      payload: { products: scored.slice(0, 3), scenarios: detectedScenarios },
    }
  }

  // Step 3: Unknown intent
  return { type: 'unknown', payload: {} }
}
