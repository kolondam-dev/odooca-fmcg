import { render } from "preact";
import "./style.css";
import { App } from "./App";
render(<App />, document.getElementById("app")!);
if ("serviceWorker" in navigator && import.meta.env.PROD) {
    window.addEventListener("load", () => {
        navigator.serviceWorker
            .register("/field/sw.js", { scope: "/field/" })
            .catch(() => {
                console.info(
                    "Offline shell unavailable; business drafts still use IndexedDB.",
                );
            });
    });
}
