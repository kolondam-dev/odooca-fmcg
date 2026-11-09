import type { ButtonHTMLAttributes } from "preact";
import { Icon, type IconName } from "../components/Icon";
import { cx } from "./cx";

export type IconButtonProps = Omit<
    ButtonHTMLAttributes<HTMLButtonElement>,
    "icon" | "children" | "type"
> & {
    icon: IconName;
    /** Wajib: nama tombol untuk pembaca layar. */
    label: string;
    /** Bingkai kotak dengan garis tipis. */
    box?: boolean;
    /** Lencana angka di pojok; 0 atau kosong menyembunyikannya. */
    badge?: number;
    type?: "button" | "submit" | "reset";
};

/** Tombol ikon 44×44 px. */
export function IconButton({
    icon,
    label,
    box,
    badge,
    type = "button",
    class: className,
    ...rest
}: IconButtonProps) {
    return (
        <button
            {...rest}
            type={type}
            aria-label={label}
            class={cx(
                "ui-iconbtn",
                box && "ui-iconbtn--box",
                className as string | undefined,
            )}
        >
            <Icon name={icon} size={24} />
            {badge ? <span class="ui-iconbtn__badge">{badge}</span> : null}
        </button>
    );
}
