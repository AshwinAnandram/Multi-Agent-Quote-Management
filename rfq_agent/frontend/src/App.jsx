import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import BidListPage from "./pages/BidListPage";
import BidDetailPage from "./pages/BidDetailPage";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <h1>Quote Management</h1>
        </header>

        <Routes>
          <Route
            path="/bids"
            element={<BidListPage />}
          />

          <Route
            path="/bids/:bidId"
            element={<BidDetailPage />}
          />

          <Route
            path="*"
            element={<Navigate to="/bids" replace />}
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;