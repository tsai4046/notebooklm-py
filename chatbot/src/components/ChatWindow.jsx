import { useRef, useEffect } from 'react'
import MessageBubble from './MessageBubble.jsx'

function TypingIndicator() {
  return (
    <div className="flex items-end gap-2">
      <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center text-sm flex-shrink-0">
        🌿
      </div>
      <div className="bg-white border border-stone-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center h-4">
          <span className="w-1.5 h-1.5 rounded-full bg-stone-400 animate-bounce [animation-delay:0ms]" />
          <span className="w-1.5 h-1.5 rounded-full bg-stone-400 animate-bounce [animation-delay:150ms]" />
          <span className="w-1.5 h-1.5 rounded-full bg-stone-400 animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  )
}

export default function ChatWindow({ messages, isTyping }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  return (
    <div
      role="log"
      aria-live="polite"
      aria-label="聊天記錄"
      className="flex-1 overflow-y-auto px-4 py-5 flex flex-col gap-4 bg-cream-50"
    >
      {messages.map(msg => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isTyping && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  )
}
