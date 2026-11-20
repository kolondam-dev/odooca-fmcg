import { Icon } from "./Icon";
import { unitLabel, type UnitParts } from "../domain/unit-qty";

type Props = Partial<UnitParts> & {
    /** sm = baris daftar, md = kartu. */
    size?: "sm" | "md";
    /** mute = stok, ink = jumlah dipesan, bad = kekurangan, ok = tersedia. */
    tone?: "mute" | "ink" | "bad" | "ok";
    /** Teks bila semua tingkat nol. */
    zero?: string;
};

/**
 * Jumlah satuan campuran sebagai badge: [karton] 1  [pack] 2  [@] 3.
 * Hanya tingkat > 0 yang tampil, urutan tetap karton → pack → pcs.
 * Pembaca layar mendapat teks utuh ("1 karton, 2 pack, 3 pcs").
 */
export function UnitQty({
    carton = 0,
    pack = 0,
    pcs = 0,
    size = "sm",
    tone = "mute",
    zero = "0",
}: Props) {
    const label = unitLabel({ carton, pack, pcs });
    const cls = `ui-unitqty ui-unitqty--${size} ui-unitqty--${tone}`;
    if (carton <= 0 && pack <= 0 && pcs <= 0) {
        return (
            <span class={cls} role="img" aria-label={zero}>
                <span class="ui-unitqty__zero" aria-hidden="true">
                    {zero}
                </span>
            </span>
        );
    }
    const px = size === "md" ? 16 : 14;
    return (
        <span class={cls} role="img" aria-label={label}>
            {carton > 0 ? (
                <span class="ui-unitqty__b" aria-hidden="true">
                    <Icon name="carton" size={px} />
                    {carton}
                </span>
            ) : null}
            {pack > 0 ? (
                <span class="ui-unitqty__b" aria-hidden="true">
                    <Icon name="pack" size={px} />
                    {pack}
                </span>
            ) : null}
            {pcs > 0 ? (
                <span class="ui-unitqty__b" aria-hidden="true">
                    <span class="ui-unitqty__at">@</span>
                    {pcs}
                </span>
            ) : null}
        </span>
    );
}

/** Legenda arti ikon satuan; tampil sekali per layar. */
export function UnitLegend() {
    return (
        <p class="ui-unitlegend">
            <Icon name="carton" size={14} /> karton ·{" "}
            <Icon name="pack" size={14} /> pack/inner ·{" "}
            <span class="ui-unitqty__at">@</span> pcs
        </p>
    );
}
