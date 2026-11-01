import { createContext } from "preact";
import { useContext, useLayoutEffect, useRef, useState } from "preact/hooks";
export type ViewMemory = Map<string, unknown>;
export const ViewMemoryContext = createContext<ViewMemory | undefined>(
    undefined,
);
// Ephemeral, scoped by the mounted authenticated workspace; never persisted.
export function useRememberedState<T>(
    key: string,
    initial: T,
): [T, (value: T) => void] {
    const memory = useContext(ViewMemoryContext);
    const [value, setValue] = useState<T>(() =>
        memory?.has(key) ? (memory.get(key) as T) : initial,
    );
    return [
        value,
        (next) => {
            memory?.set(key, next);
            setValue(next);
        },
    ];
}
export function useRememberedScroll<T extends HTMLElement = HTMLElement>(
    key: string,
    supplied?: ViewMemory,
) {
    const context = useContext(ViewMemoryContext),
        memory = supplied ?? context;
    const root = useRef<T>(null);
    useLayoutEffect(() => {
        const element = root.current;
        if (!element) return;
        element.scrollTop = Number(memory?.get(key) ?? 0);
        const save = () => memory?.set(key, element.scrollTop);
        element.addEventListener("scroll", save, { passive: true });
        return () => {
            element.removeEventListener("scroll", save);
        };
    }, [key, memory]);
    return root;
}
