import type { ButtonHTMLAttributes, ComponentChildren } from "preact";
import { Icon, type IconName } from "../components/Icon";
import { cx } from "./cx";

export type ButtonVariant = "pri" | "sec" | "danger";
export type ButtonSize = "lg" | "md" | "sm";

export type ButtonProps = Omit<
    ButtonHTMLAttributes<HTMLButtonElement>,
    "size" | "icon" | "type"
> & {
    variant?: ButtonVariant;
    /** lg 56 px, md 48 px, sm 44 px. */
    size?: ButtonSize;
    icon?: IconName;
    /** Lebar mengikuti isi, bukan penuh. */
    auto?: boolean;
    type?: "button" | "submit" | "reset";
    children?: ComponentChildren;
};

/** Tombol aksi. Nonaktif memakai atribut disabled asli, bukan hanya gaya. */
export function Button({
    variant = "pri",
    size = "lg",
    icon,
    auto,
    type = "button",
    class: className,
    children,
    ...rest
}: ButtonProps) {
    return (
        <button
            {...rest}
            type={type}
            class={cx(
                "ui-btn",
                `ui-btn--${variant}`,
                `ui-btn--${size}`,
                auto && "ui-btn--auto",
                className as string | undefined,
            )}
        >
            {icon ? <Icon name={icon} size={20} /> : null}
            {children}
        </button>
    );
}
