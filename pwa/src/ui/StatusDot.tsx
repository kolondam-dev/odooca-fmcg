import { cx } from "./cx";

/** Titik status koneksi. Selalu disertai teks di dekatnya atau label. */
export function StatusDot({
    online,
    label,
}: {
    online: boolean;
    label?: string;
}) {
    return (
        <span
            class={cx("ui-dot", !online && "is-off")}
            role="img"
            aria-label={label ?? (online ? "Online" : "Offline")}
        />
    );
}
