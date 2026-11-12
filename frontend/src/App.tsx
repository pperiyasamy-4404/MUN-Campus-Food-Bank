import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router'
import { Layout, StaffOnly, StudentOnly } from './Layout.tsx'
import { MeProvider } from './MeProvider.tsx'
import { Book } from './pages/Book.tsx'
import { FixPickup } from './pages/FixPickup.tsx'
import { HandOver } from './pages/HandOver.tsx'
import { ManageDays } from './pages/ManageDays.tsx'
import { Home } from './pages/Home.tsx'
import { StaffLogIn, StudentLogIn } from './pages/LogIn.tsx'
import { PackBag } from './pages/PackBag.tsx'
import { Packing } from './pages/Packing.tsx'
import { SetupCode } from './pages/SetupCode.tsx'
import { Settings } from './pages/Settings.tsx'
import { StaffSetUp, StudentSetUp } from './pages/SetUp.tsx'
import { Stock } from './pages/Stock.tsx'
import { Totals } from './pages/Totals.tsx'
import { Volunteers } from './pages/Volunteers.tsx'
import { WalkIn } from './pages/WalkIn.tsx'
import { PageHeading } from './PageHeading.tsx'
import { StyleGuide } from './pages/StyleGuide.tsx'

// Every page and its web address. The addresses never hold anything private:
// no ID numbers, no codes (P10).

function App() {
  return (
    <BrowserRouter>
      <MeProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="login" element={<StudentLogIn />} />
            <Route path="setup" element={<StudentSetUp />} />
            <Route path="staff/login" element={<StaffLogIn />} />
            <Route path="staff/setup" element={<StaffSetUp />} />
            <Route
              path="book"
              element={
                <StudentOnly>
                  <Book />
                </StudentOnly>
              }
            />
            <Route
              path="counter"
              element={
                <StaffOnly>
                  <HandOver />
                </StaffOnly>
              }
            />
            <Route
              path="counter/walk-in"
              element={
                <StaffOnly>
                  <WalkIn />
                </StaffOnly>
              }
            />
            <Route
              path="counter/fix"
              element={
                <StaffOnly>
                  <FixPickup />
                </StaffOnly>
              }
            />
            <Route
              path="counter/setup-code"
              element={
                <StaffOnly>
                  <SetupCode />
                </StaffOnly>
              }
            />
            <Route
              path="stock"
              element={
                <StaffOnly>
                  <Stock />
                </StaffOnly>
              }
            />
            <Route
              path="packing"
              element={
                <StaffOnly>
                  <Packing />
                </StaffOnly>
              }
            />
            <Route
              path="packing/:bookingId"
              element={
                <StaffOnly>
                  <PackBag />
                </StaffOnly>
              }
            />
            <Route
              path="coordinator"
              element={
                <StaffOnly coordinator>
                  <ManageDays />
                </StaffOnly>
              }
            />
            <Route
              path="coordinator/totals"
              element={
                <StaffOnly coordinator>
                  <Totals />
                </StaffOnly>
              }
            />
            <Route
              path="coordinator/settings"
              element={
                <StaffOnly coordinator>
                  <Settings />
                </StaffOnly>
              }
            />
            <Route
              path="coordinator/volunteers"
              element={
                <StaffOnly coordinator>
                  <Volunteers />
                </StaffOnly>
              }
            />
            <Route path="volunteers" element={<Navigate to="/coordinator/volunteers" replace />} />
            {/* Development only: every colour, button, badge and alert on one page (MUN theme, 12 Nov). */}
            {import.meta.env.DEV && <Route path="style-guide" element={<StyleGuide />} />}
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </MeProvider>
    </BrowserRouter>
  )
}

function NotFound() {
  return (
    <div className="narrow">
      <PageHeading>There's no page here</PageHeading>
      <p>
        <Link to="/">Go to the pickup days</Link>
      </p>
    </div>
  )
}

export default App
