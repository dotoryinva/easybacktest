import type { ChatMessage } from '../../schemas/strategy'

type Props = {
  history: ChatMessage[]
  pending?: boolean
}

export function ConversationThread({ history, pending }: Props) {
  if (history.length === 0 && !pending) return null

  return (
    <div className="space-y-3">
      {history.map((message, index) => (
        <div
          key={index}
          className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              message.role === 'user'
                ? 'rounded-br-sm bg-accent text-white'
                : 'rounded-bl-sm border border-ink-700 bg-ink-850 text-primary'
            }`}
          >
            {message.content}
          </div>
        </div>
      ))}
      {pending && (
        <div className="flex justify-start">
          <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-ink-700 bg-ink-850 px-4 py-3">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500"
                style={{ animationDelay: `${i * 120}ms` }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
