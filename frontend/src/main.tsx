import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./Layout";
import Landing from "./Landing";
import AuthPage from "./AuthPage";
import { AuthProvider, Protected } from "./auth";
import Home from "./Home";
import RatingVsText from "./RatingVsText";
import Problems from "./Problems";
import Aspects from "./Aspects";
import Compare from "./Compare";
import Explorer from "./Explorer";
import Upload from "./Upload";
import Quality from "./Quality";
import Extras from "./Extras";
import Sentiment from "./Sentiment";
import Distribution from "./Distribution";
import Listing from "./Listing";
import Label from "./Label";
import Reports from "./Reports";
import Trends from "./Trends";
import "./index.css";

const client = new QueryClient();
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <AuthProvider>
        <Routes>
          <Route path="welcome" element={<Landing />} />
          <Route path="login" element={<AuthPage mode="login" />} />
          <Route path="signup" element={<AuthPage mode="signup" />} />
          <Route element={<Protected />}>
          <Route element={<Layout />}>
            {/* landing-upload: open on Upload, not on old results */}
            <Route index element={<Navigate to="/upload" replace />} />
            <Route path="home" element={<Home />} />
            <Route path="rating-vs-text" element={<RatingVsText />} />
            <Route path="problems" element={<Problems />} />
            <Route path="aspects" element={<Aspects />} />
            <Route path="compare" element={<Compare />} />
            <Route path="explorer" element={<Explorer />} />
            <Route path="upload" element={<Upload />} />
            <Route path="quality" element={<Quality />} />
            <Route path="checks" element={<Extras />} />
            <Route path="sentiment" element={<Sentiment />} />
            <Route path="distribution" element={<Distribution />} />
            <Route path="label" element={<Label />} />
            <Route path="reports" element={<Reports />} />
            <Route path="listing" element={<Listing />} />
            <Route path="trends" element={<Trends />} />
            <Route path="*" element={<div className="p-8 text-slate-500">This page arrives in a later step.</div>} />
          </Route>
          </Route>
        </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);

