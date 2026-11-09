import type { ComponentChildren } from "preact";
import { useDialog } from "./useDialog";
import { useBackLayer } from "./navigation";

/** Lembar bawah DS: scrim, pegangan, judul. Fokus terkunci dan Back menutupnya. */
export function BottomSheet({
    title,
    onClose,
    children,
}: {
    title: string;
    onClose: () => void;
    children: ComponentChildren;
}) {
    const root = useDialog<HTMLDivElement>(onClose);
    useBackLayer(true, onClose);
    return (
        <div
            class="ui-scrim"
            ref={root}
            role="dialog"
            aria-modal="true"
            aria-label={title}
        >
            <button
                type="button"
                class="ui-scrim__hit"
                aria-label="Tutup"
                onClick={onClose}
            />
            <section class="ui-sheet">
                <span class="ui-sheet__grab" aria-hidden="true" />
                <h2 class="ui-sheet__title">{title}</h2>
                {children}
            </section>
        </div>
    );
}
