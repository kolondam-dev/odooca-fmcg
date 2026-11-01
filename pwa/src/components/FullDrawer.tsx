import type { ComponentChildren } from "preact";
import { useLayoutEffect, useRef } from "preact/hooks";
import { Icon } from "./Icon";
export function FullDrawer({
    title,
    close,
    children,
}: {
    title: string;
    close: () => void;
    children: ComponentChildren;
}) {
    const root = useRef<HTMLElement>(null),
        origin = useRef(document.activeElement as HTMLElement | null);
    useLayoutEffect(() => {
        const behind: { element: HTMLElement; inert: boolean }[] = [];
        let branch: HTMLElement | null = root.current;
        while (branch?.parentElement) {
            for (const sibling of branch.parentElement.children) {
                if (sibling !== branch && sibling instanceof HTMLElement) {
                    behind.push({ element: sibling, inert: sibling.inert });
                    sibling.inert = true;
                }
            }
            if (branch.parentElement === document.body) break;
            branch = branch.parentElement;
        }
        const overflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        (
            root.current?.querySelector<HTMLElement>("input") ??
            root.current?.querySelector<HTMLElement>("button")
        )?.focus();
        const keys = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                event.preventDefault();
                close();
            }
            if (event.key !== "Tab") return;
            const items = [
                ...root.current!.querySelectorAll<HTMLElement>(
                    "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]",
                ),
            ].filter((el) => el.getClientRects().length);
            const first = items[0],
                last = items.at(-1);
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
            }
        };
        document.addEventListener("keydown", keys);
        return () => {
            behind
                .reverse()
                .forEach(({ element, inert }) => (element.inert = inert));
            document.body.style.overflow = overflow;
            document.removeEventListener("keydown", keys);
            requestAnimationFrame(() => {
                if (origin.current?.isConnected) origin.current.focus();
            });
        };
    }, []);
    return (
        <section
            ref={root}
            class="workflow-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={title}
        >
            <header>
                <h2>{title}</h2>
                <button
                    type="button"
                    class="icon-button"
                    onClick={close}
                    aria-label={`Tutup ${title}`}
                >
                    <Icon name="close" />
                </button>
            </header>
            <div class="workflow-drawer-body">{children}</div>
        </section>
    );
}
