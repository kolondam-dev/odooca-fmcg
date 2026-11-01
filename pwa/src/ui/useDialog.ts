import { useLayoutEffect, useRef } from "preact/hooks";

// Stack ownership matters: a camera opened inside a form must be the only
// keyboard target; closing it restores both the form's inert state and focus.
const stack: HTMLElement[] = [];
export function useDialog<T extends HTMLElement = HTMLElement>(
    close: () => void,
) {
    const root = useRef<T>(null);
    const latest = useRef(close);
    latest.current = close;
    useLayoutEffect(() => {
        const dialog = root.current!;
        const origin = document.activeElement as HTMLElement | null;
        const hidden: {
            el: HTMLElement;
            inert: boolean;
            modal: string | null;
        }[] = [];
        let branch: HTMLElement | null = dialog;
        while (branch?.parentElement) {
            const parent: HTMLElement = branch.parentElement;
            for (const sibling of parent.children) {
                if (sibling !== branch && sibling instanceof HTMLElement) {
                    hidden.push({
                        el: sibling,
                        inert: sibling.inert,
                        modal: null,
                    });
                    sibling.inert = true;
                }
            }
            if (parent.getAttribute("role") === "dialog") {
                hidden.push({
                    el: parent,
                    inert: parent.inert,
                    modal: parent.getAttribute("aria-modal"),
                });
                parent.setAttribute("aria-modal", "false");
            }
            if (parent === document.body) break;
            branch = parent;
        }
        stack.push(dialog);
        const overflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const focusable = () =>
            [
                ...dialog.querySelectorAll<HTMLElement>(
                    'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]',
                ),
            ].filter(
                (el) =>
                    el.getClientRects().length &&
                    !el.closest("[inert]") &&
                    getComputedStyle(el).visibility !== "hidden",
            );
        (
            dialog.querySelector<HTMLElement>("[autofocus]") ??
            focusable()[0] ??
            dialog
        ).focus();
        const keydown = (e: KeyboardEvent) => {
            if (stack.at(-1) !== dialog) return;
            if (e.key === "Escape") {
                e.preventDefault();
                e.stopImmediatePropagation();
                latest.current();
            }
            if (e.key !== "Tab") return;
            const items = focusable(),
                first = items[0],
                last = items.at(-1);
            if (!first) {
                e.preventDefault();
                dialog.focus();
            } else if (
                e.shiftKey &&
                (document.activeElement === first ||
                    !dialog.contains(document.activeElement))
            ) {
                e.preventDefault();
                last?.focus();
            } else if (
                !e.shiftKey &&
                (document.activeElement === last ||
                    !dialog.contains(document.activeElement))
            ) {
                e.preventDefault();
                first.focus();
            }
        };
        document.addEventListener("keydown", keydown, true);
        return () => {
            stack.splice(stack.indexOf(dialog), 1);
            document.removeEventListener("keydown", keydown, true);
            hidden.reverse().forEach(({ el, inert, modal }) => {
                el.inert = inert;
                if (modal !== null) el.setAttribute("aria-modal", modal);
            });
            document.body.style.overflow = overflow;
            requestAnimationFrame(() => {
                if (origin?.isConnected && !origin.closest("[inert]"))
                    origin.focus();
            });
        };
    }, []);
    return root;
}
