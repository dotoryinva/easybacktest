export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-400">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-ink-600 border-t-accent"
        role="status"
        aria-label={label ?? 'Loading'}
      />
      {label && <span>{label}</span>}
    </div>
  )
}
