import React from "react";
import ReactDOM from "react-dom/client";
import CorrespondenceApp from "./auth/CorrespondenceApp";
import "@fontsource-variable/plus-jakarta-sans/wght.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <CorrespondenceApp />
  </React.StrictMode>,
);
