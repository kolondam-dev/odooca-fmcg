import type { ComponentChildren } from "preact";
import { Icon, type IconName } from "../components/Icon";
import { cx } from "./cx";

export type Tone = "ok" | "warn" | "bad" | "info" | "neu";

/** Lencana status. Warna tidak boleh menjadi satu-satunya penanda: sertakan teks. */
export function Chip({
    tone = "neu",
    icon,
    children,
}: {
    tone?: Tone;
    icon?: IconName;
    children: ComponentChildren;
}) {
    return (
        <span class={cx("ui-chip", `ui-chip--${tone}`)}>
            {icon ? <Icon name={icon} size={14} /> : null}
            {children}
        </span>
    );
}
