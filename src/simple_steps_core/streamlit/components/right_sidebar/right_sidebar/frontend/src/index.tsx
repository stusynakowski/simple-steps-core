import React from "react"
import ReactDOM from "react-dom/client"
import RightSidebarToggle from "./RightSidebarToggle"

const root = ReactDOM.createRoot(
  document.getElementById("root") as HTMLElement
)
root.render(
  <React.StrictMode>
    <RightSidebarToggle />
  </React.StrictMode>
)
