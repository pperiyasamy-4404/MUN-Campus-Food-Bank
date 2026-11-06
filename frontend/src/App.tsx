import { BrowserRouter, Link, Route, Routes } from 'react-router'
import { Layout, StaffOnly, StudentOnly } from './Layout.tsx'
import { MeProvider } from './MeProvider.tsx'
import { Book } from './pages/Book.tsx'
import { Counter } from './pages/Counter.tsx'
import { Home } from './pages/Home.tsx'
import { StaffLogIn, StudentLogIn } from './pages/LogIn.tsx'
import { StaffSetUp, StudentSetUp } from './pages/SetUp.tsx'
import { Stock } from './pages/Stock.tsx'
import { Volunteers } from './pages/Volunteers.tsx'

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
                  <Counter />
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
              path="volunteers"
              element={
                <StaffOnly coordinator>
                  <Volunteers />
                </StaffOnly>
              }
            />
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
      <h1>There's no page here</h1>
      <p>
        <Link to="/">Go to the pickup days</Link>
      </p>
    </div>
  )
}

export default App
