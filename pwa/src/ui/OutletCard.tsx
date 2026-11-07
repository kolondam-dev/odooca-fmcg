import type { ComponentChildren } from "preact";
import { Chip, type Tone } from "./Chip";
import { cx } from "./cx";

export type OutletCardProps = {
    /** Urutan kunjungan pada rencana hari ini. */
    number: number;
    name: string;
    address: string;
    status: { tone: Tone; label: string };
    /** Sorot kartu: outlet berikutnya. */
    highlight?: boolean;
    /** Baris info tambahan (jam, jarak, tagihan). */
    meta?: ComponentChildren;
    onClick?: () => void;
};

/** Kartu outlet pada daftar kunjungan (DS: ocard). */
export function OutletCard({
    number,
    name,
    address,
    status,
    highlight,
    meta,
    onClick,
}: OutletCardProps) {
    return (
        <button
            type="button"
            class={cx("ui-ocard", highlight && "is-hl")}
            onClick={onClick}
        >
            <span class="ui-ocard__num" aria-hidden="true">
                {number}
            </span>
            <span class="ui-ocard__body">
                <span class="ui-ocard__top">
                    <strong class="ui-ocard__name">{name}</strong>
                    <Chip tone={status.tone}>{status.label}</Chip>
                </span>
                <span class="ui-ocard__addr">{address}</span>
                {meta ? <span class="ui-ocard__meta">{meta}</span> : null}
            </span>
        </button>
    );
}
