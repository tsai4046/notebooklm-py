import { useState, useCallback } from 'react'
import { detect } from '../engine/intentEngine.js'

const SCENARIO_LABELS = {
  relax: '放鬆',
  sleep: '助眠',
  focus: '專注',
  nature: '大自然',
  fresh: '清新',
  gift: '送禮',
}

const FOLLOW_UPS = [
  '您好！請問您是想放鬆、助眠、還是提升專注力呢？我可以幫您找到最適合的香氛 🌿',
  '請問您的使用場景是什麼呢？例如：在家放鬆、工作提神、睡前助眠，或是要送禮？',
  '請問您是為自己選購，還是有送禮需求呢？告訴我更多，我來幫您推薦！',
]

let idCounter = 1
function nextId() { return idCounter++ }

const WELCOME = {
  id: nextId(),
  role: 'bot',
  type: 'text',
  text: '您好！我是 AromaSense AI 🌸\n\n我可以幫您找到最適合的香氛商品，或解答任何關於精油與香氛的問題。\n\n您可以直接描述您的需求，或點選下方快速按鈕開始探索 ✨',
  timestamp: Date.now(),
}

export function useChat() {
  const [messages, setMessages] = useState([WELCOME])
  const [products, setProducts] = useState(null)
  const [isTyping, setIsTyping] = useState(false)
  const [followUpIndex, setFollowUpIndex] = useState(0)

  const appendMessage = useCallback((msg) => {
    setMessages(prev => [...prev, { id: nextId(), timestamp: Date.now(), ...msg }])
  }, [])

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isTyping) return

    appendMessage({ role: 'user', type: 'text', text: text.trim() })
    setIsTyping(true)

    await new Promise(r => setTimeout(r, 700))

    const intent = detect(text)

    if (intent.type === 'faq') {
      appendMessage({ role: 'bot', type: 'text', text: intent.payload.answer })
      setProducts(null)
    } else if (intent.type === 'recommend') {
      const labels = intent.payload.scenarios.map(s => SCENARIO_LABELS[s] || s).join('＆')
      appendMessage({
        role: 'bot',
        type: 'text',
        text: `為您找到最適合「${labels}」的香氛推薦 ✨`,
      })
      setProducts(intent.payload.products)
    } else {
      const reply = FOLLOW_UPS[followUpIndex % FOLLOW_UPS.length]
      appendMessage({ role: 'bot', type: 'text', text: reply })
      setFollowUpIndex(i => i + 1)
      setProducts(null)
    }

    setIsTyping(false)
  }, [isTyping, appendMessage, followUpIndex])

  const handleQuickSelect = useCallback((key) => {
    const label = SCENARIO_LABELS[key] || key
    sendMessage(label)
  }, [sendMessage])

  return { messages, products, isTyping, sendMessage, handleQuickSelect }
}
