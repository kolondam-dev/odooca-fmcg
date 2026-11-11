import type { ComponentChildren } from "preact";
import { Icon, type IconName } from "../components/Icon";
import { Chip, type Tone } from "./Chip";
import { cx } from "./cx";

export function Card({
    children,
    tight,
    class: className,
}: {
    children: ComponentChildren;
    tight?: boolean;
    class?: string;
}) {
    return (
        <div class={cx("ui-card", tight && "ui-card--tight", className)}>
            {children}
        </div>
    );
}

/** Judul kartu dengan chip status di kanan. */
export function CardHead({
    title,
    status,
}: {
    title: string;
    status?: { tone: Tone; label: string };
}) {
    return (
        <div class="ui-cardhead">
            <h2 class="ui-cardhead__t">{title}</h2>
            {status ? <Chip tone={status.tone}>{status.label}</Chip> : null}
        </div>
    );
}

/** Baris daftar: ubin ikon, judul, subjudul, status/panah. */
export function ListRow({
    icon,
    title,
    sub,
    status,
    onClick,
    disabled,
    divider,
}: {
    /** Tanpa ikon: baris teks (DS: Uang_lapangan, Riwayat). */
    icon?: IconName;
    title: string;
    sub?: string;
    status?: { tone: Tone; label: string };
    onClick?: () => void;
    disabled?: boolean;
    divider?: boolean;
}) {
    const inner = (
        <>
            {icon ? (
                <span class="ui-row__tile">
                    <Icon name={icon} size={22} />
                </span>
            ) : null}
            <span class="ui-row__body">
                <span class="ui-row__title">{title}</span>
                {sub ? <span class="ui-row__sub">{sub}</span> : null}
            </span>
            {status ? <Chip tone={status.tone}>{status.label}</Chip> : null}
            {onClick ? <Icon name="caret" size={18} /> : null}
        </>
    );
    const c = cx("ui-row", divider && "ui-row--div");
    return onClick ? (
        <button type="button" class={c} onClick={onClick} disabled={disabled}>
            {inner}
        </button>
    ) : (
        <div class={c}>{inner}</div>
    );
}

export function Callout({
    tone = "info",
    icon,
    title,
    children,
    alert,
}: {
    alert?: boolean;
    tone?: "info" | "warn" | "bad" | "neu";
    icon?: IconName;
    title?: string;
    children: ComponentChildren;
}) {
    return (
        <div
            class={cx("ui-callout", `ui-callout--${tone}`)}
            role={alert ? "alert" : "status"}
        >
            {icon ? <Icon name={icon} size={20} /> : null}
            <span class="ui-callout__body">
                {title ? <strong>{title}</strong> : null}
                {children}
            </span>
        </div>
    );
}

export function KV({
    label,
    value,
    tone,
}: {
    label: string;
    value: ComponentChildren;
    tone?: "ok" | "warn";
}) {
    return (
        <div class="ui-kv">
            <span>{label}</span>
            <strong class={tone ? `is-${tone}` : undefined}>{value}</strong>
        </div>
    );
}
