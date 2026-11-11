import { NavLink } from 'react-router'

/** The coordinators' pages (R3). */
export function CoordinatorNav() {
  return (
    <nav className="sub-nav" aria-label="Coordinator">
      <NavLink to="/coordinator" end>
        Pickup days
      </NavLink>
      <NavLink to="/coordinator/totals">Weekly totals</NavLink>
      <NavLink to="/coordinator/settings">Settings</NavLink>
      <NavLink to="/coordinator/volunteers">Staff</NavLink>
    </nav>
  )
}
