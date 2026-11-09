import type { ComponentChildren } from "preact";
import { Chip, type Tone } from "./Chip";
import { IconButton } from "./IconButton";
import { cx } from "./cx";

/** Kepala layar: tombol kembali 44 px, judul, chip status opsional. */
export function ScreenHeader({
    title,
    onBack,
    status,
    right,
}: {
    title: string;
    onBack: () => void;
    status?: { tone: Tone; label: string };
    right?: ComponentChildren;
}) {
    return (
        <header class="ui-hdr">
            <IconButton
                icon="caret"
                label="Kembali"
                class="ui-hdr__back"
                onClick={onBack}
            />
            <h1 class="ui-hdr__title">{title}</h1>
            {status ? <Chip tone={status.tone}>{status.label}</Chip> : null}
            <span class="ui-hdr__gap" />
            {right}
        </header>
    );
}

/** Layar penuh DS: header, (tracker), badan yang bergulir, bilah aksi bawah. */
export function Screen({
    label,
    header,
    sub,
    footer,
    children,
    flush,
    class: className,
}: {
    label: string;
    header: ComponentChildren;
    /** Di bawah header, mis. Tracker. */
    sub?: ComponentChildren;
    footer?: ComponentChildren;
    children: ComponentChildren;
    /** Badan tanpa padding (peta penuh). */
    flush?: boolean;
    class?: string;
}) {
    return (
        <section class={cx("ui-screen", className)} aria-label={label}>
            {header}
            {sub}
            <div class={cx("ui-screen__body", flush && "is-flush")}>
                {children}
            </div>
            {footer ? <div class="ui-actionbar">{footer}</div> : null}
        </section>
    );
}

/** Teks bantu di atas/bawah tombol aksi. */
export function ActionCaption({ children }: { children: ComponentChildren }) {
    return (
        <p class="ui-actionbar__cap" role="status">
            {children}
        </p>
    );
}
