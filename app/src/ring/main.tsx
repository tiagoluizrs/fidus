import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RingApp } from "./RingApp";
import "./ring.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RingApp />
  </StrictMode>,
);
