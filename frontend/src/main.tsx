import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

function App() {
  return <main aria-label="PD Agent preview">PD Agent v0.9</main>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
