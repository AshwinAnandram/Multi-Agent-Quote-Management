import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import BidListPage from "./pages/BidListPage";
import BidDetailPage from "./pages/BidDetailPage";
import RFQReviewPage from "./pages/RFQReviewPage";
import CustomerCreatePage from "./pages/CustomerCreatePage";
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
            path="/rfqs/:rfqId/review"
            element={<RFQReviewPage />}
          />

          <Route
            path="/rfqs/:rfqId/customers/new"
            element={<CustomerCreatePage />}
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
