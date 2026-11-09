import { cx } from "./cx";

export type SegmentedItem<T extends string> = {
    value: T;
    label: string;
    disabled?: boolean;
};

/** Dua sampai empat pilihan eksklusif. Tombol memakai aria-pressed seperti .segmented lama. */
export function Segmented<T extends string>({
    items,
    value,
    onChange,
    label,
}: {
    items: Array<SegmentedItem<T>>;
    value: T;
    onChange: (value: T) => void;
    /** Nama grup untuk pembaca layar. */
    label: string;
}) {
    return (
        <div class="ui-seg" role="group" aria-label={label}>
            {items.map((item) => (
                <button
                    key={item.value}
                    type="button"
                    class={cx("ui-seg__item", item.value === value && "is-on")}
                    aria-pressed={item.value === value}
                    disabled={item.disabled}
                    onClick={() => onChange(item.value)}
                >
                    {item.label}
                </button>
            ))}
        </div>
    );
}
