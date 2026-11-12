import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./Layout";
import Home from "./Home";
import RatingVsText from "./RatingVsText";
import Problems from "./Problems";
import Aspects from "./Aspects";
import Compare from "./Compare";
import Explorer from "./Explorer";
import Upload from "./Upload";
import Trends from "./Trends";
import "./index.css";

const client = new QueryClient();
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="rating-vs-text" element={<RatingVsText />} />
            <Route path="problems" element={<Problems />} />
            <Route path="aspects" element={<Aspects />} />
            <Route path="compare" element={<Compare />} />
            <Route path="explorer" element={<Explorer />} />
            <Route path="upload" element={<Upload />} />
            <Route path="trends" element={<Trends />} />
            <Route path="*" element={<div className="p-8 text-slate-500">This page arrives in a later step.</div>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);

