import type { ComponentChildren } from "preact";

/** Kotak centang; seluruh baris, termasuk teks, dapat disentuh (≥44 px). */
export function Checkbox({
    checked,
    onChange,
    children,
    label,
    disabled,
}: {
    checked: boolean;
    onChange: (checked: boolean) => void;
    children?: ComponentChildren;
    /** Dipakai bila tidak ada teks terlihat. */
    label?: string;
    disabled?: boolean;
}) {
    return (
        <label class="ui-check">
            <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                aria-label={children ? undefined : label}
                onChange={(event) =>
                    onChange((event.currentTarget as HTMLInputElement).checked)
                }
            />
            {children}
        </label>
    );
}
