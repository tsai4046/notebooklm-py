import Header from './components/Header.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import ProductList from './components/ProductList.jsx'
import QuickButtons from './components/QuickButtons.jsx'
import InputBar from './components/InputBar.jsx'
import { useChat } from './hooks/useChat.js'

export default function App() {
  const { messages, products, isTyping, sendMessage, handleQuickSelect } = useChat()

  return (
    <div className="h-screen flex flex-col max-w-2xl mx-auto bg-white shadow-warm">
      <Header />
      <ChatWindow messages={messages} isTyping={isTyping} />
      <ProductList products={products} />
      <QuickButtons onQuickSelect={handleQuickSelect} />
      <InputBar onSend={sendMessage} disabled={isTyping} />
    </div>
  )
}
