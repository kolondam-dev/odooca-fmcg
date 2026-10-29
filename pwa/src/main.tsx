import { render } from "preact";
import "./style.css";
if (__READ_ONLY__) {
    // Retire any previous /field/ shell before connecting a real session.
    async function openReadApp() {
        if ("serviceWorker" in navigator) {
            const registrations =
                await navigator.serviceWorker.getRegistrations();
            await Promise.all(
                registrations
                    .filter(
                        (registration) =>
                            registration.scope ===
                            new URL("/field/", location.origin).href,
                    )
                    .map((registration) => registration.unregister()),
            );
        }
        if ("caches" in window) {
            const keys = await caches.keys();
            await Promise.all(
                keys
                    .filter((key) => key.startsWith("fmcg-field-"))
                    .map((key) => caches.delete(key)),
            );
        }
        const { ReadApp } = await import("./ReadApp");
        render(<ReadApp />, document.getElementById("app")!);
    }
    void openReadApp().catch(() => {
        document.getElementById("app")!.textContent =
            "Tampilan staging belum dapat dibuka. Tutup tab dan coba kembali.";
    });
} else {
    import("./App").then(({ App }) =>
        render(<App />, document.getElementById("app")!),
    );
}
if (!__READ_ONLY__ && "serviceWorker" in navigator && import.meta.env.PROD) {
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
