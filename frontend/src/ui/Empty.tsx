import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon.tsx'

/** A friendly empty page: a drawing, what's going on, and what happens next (13 Nov). */
export function Empty({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Icon name={icon} className="empty-icon" />
      <p className="empty-title">{title}</p>
      {children && <p>{children}</p>}
    </div>
  )
}
