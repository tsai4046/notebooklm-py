function formatText(text) {
  return text.split('\n').map((line, i) => (
    <span key={i}>
      {line}
      {i < text.split('\n').length - 1 && <br />}
    </span>
  ))
}

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex items-end gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center text-sm flex-shrink-0 mb-1">
          🌿
        </div>
      )}
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm
          ${isUser
            ? 'bg-rose-600 text-white rounded-br-sm'
            : 'bg-white text-ink border border-stone-100 rounded-bl-sm'
          }`}
      >
        {formatText(message.text)}
      </div>
    </div>
  )
}
