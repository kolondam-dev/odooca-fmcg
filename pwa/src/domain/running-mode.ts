import { useEffect, useState } from "preact/hooks";

export type RunningMode = "demo" | "live";

export const RUNNING_MODE_KEY = "fmcg:running-mode";
export const DEMO_BANNER_TEXT =
    "Aplikasi running pada mode demo, validasi geofence dan timestamp diabaikan";

export function getRunningMode(): RunningMode {
    try {
        if (typeof window !== "undefined" && window.localStorage) {
            const stored = window.localStorage.getItem(RUNNING_MODE_KEY);
            if (stored === "demo") return "demo";
            if (stored === "live") return "live";
        }
    } catch {
        // Storage might be restricted in some sandboxes
    }
    return "live";
}

export function setRunningMode(mode: RunningMode): void {
    try {
        if (typeof window !== "undefined" && window.localStorage) {
            window.localStorage.setItem(RUNNING_MODE_KEY, mode);
            window.dispatchEvent(
                new CustomEvent("running-mode-changed", { detail: mode }),
            );
        }
    } catch {
        // Storage might be restricted
    }
}

export function isDemoMode(): boolean {
    return getRunningMode() === "demo";
}

export function useRunningMode(): [RunningMode, (mode: RunningMode) => void] {
    const [mode, setModeState] = useState<RunningMode>(getRunningMode);

    useEffect(() => {
        const handler = (event: Event) => {
            const custom = event as CustomEvent<RunningMode>;
            if (custom.detail === "demo" || custom.detail === "live") {
                setModeState(custom.detail);
            } else {
                setModeState(getRunningMode());
            }
        };

        const storageHandler = (event: StorageEvent) => {
            if (event.key === RUNNING_MODE_KEY) {
                setModeState(getRunningMode());
            }
        };

        window.addEventListener("running-mode-changed", handler);
        window.addEventListener("storage", storageHandler);
        return () => {
            window.removeEventListener("running-mode-changed", handler);
            window.removeEventListener("storage", storageHandler);
        };
    }, []);

    const updateMode = (newMode: RunningMode) => {
        setRunningMode(newMode);
        setModeState(newMode);
    };

    return [mode, updateMode];
}
