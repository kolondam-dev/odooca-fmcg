import type { ComponentChildren } from "preact";
import { useDialog } from "../ui/useDialog";
import { useBackLayer } from "../ui/navigation";
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
    const root = useDialog(close);
    useBackLayer(true, close);
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
