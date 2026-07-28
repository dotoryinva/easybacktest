import { Bell, type LucideIcon } from 'lucide-react'

type Props = {
  icon: LucideIcon
  titleKo: string
  titleEn: string
  description: string
}

export function ComingSoon({ icon: Icon, titleKo, titleEn, description }: Props) {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center gap-5 px-6 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-accent/10 text-accent">
        <Icon size={26} strokeWidth={1.75} />
      </div>
      <div className="space-y-1">
        <h1 className="text-xl font-semibold text-primary">{titleKo}</h1>
        <p className="text-sm font-medium uppercase tracking-wide text-secondary">{titleEn}</p>
      </div>
      <p className="text-sm leading-relaxed text-secondary">{description}</p>
      <a
        href="mailto:dotoryinva@gmail.com?subject=EasyBacktest%20기능%20알림%20신청"
        className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-slate-50"
      >
        <Bell size={15} />
        알림 받기
      </a>
    </div>
  )
}
