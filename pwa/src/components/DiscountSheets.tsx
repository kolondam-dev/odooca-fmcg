import { useState } from "preact/hooks";
import { money } from "../domain/format";
import type {
    DiscountProgram,
    FooterDiscount,
    LineDiscount,
} from "../domain/order-discount";
import {
    BottomSheet,
    Button,
    Callout,
    Card,
    Chip,
    Field,
    IconButton,
    Select,
    Textarea,
} from "../ui";

/** Alasan baku pengajuan; kontrak menerima teks bebas 3–500 karakter. */
export const DISCOUNT_REASONS = [
    "Pembeli minta potongan ongkos",
    "Kompetitor lebih murah",
    "Program promo belum tersedia di sistem",
    "Lainnya",
];
const TACTICAL = "tactical";

type Row = { source: string; value: string; choice: string; other: string };

function rowFrom(d: LineDiscount | FooterDiscount): Row {
    const value = String("percent" in d ? d.percent : d.amount);
    const reason = d.kind === "tactical" ? d.reason : "";
    const preset = DISCOUNT_REASONS.includes(reason);
    return {
        source: d.kind === "program" ? d.program_id : TACTICAL,
        value,
        choice: preset ? reason : reason ? "Lainnya" : DISCOUNT_REASONS[0]!,
        other: preset ? "" : reason,
    };
}

/**
 * Satu komponen untuk Diskon_baris (persen, bertingkat atas sisa harga) dan
 * Diskon_footer (Rupiah, setelah diskon baris). Program dulu, lalu pengajuan.
 */
export function DiscountSheet<T extends LineDiscount | FooterDiscount>({
    mode,
    title,
    base,
    programs,
    usedElsewhere,
    initial,
    onApply,
    onClose,
}: {
    mode: "line" | "footer";
    title: string;
    /** Line: harga kotor SKU. Footer: total setelah diskon baris. */
    base: number;
    programs: DiscountProgram[];
    /** Pemakaian budget per program oleh bagian order lain. */
    usedElsewhere: Record<string, number>;
    initial: T[];
    onApply: (next: T[]) => void;
    onClose: () => void;
}) {
    const [rows, setRows] = useState<Row[]>(() => initial.map(rowFrom));
    const set = (i: number, patch: Partial<Row>) =>
        setRows((cur) => cur.map((r, j) => (i === j ? { ...r, ...patch } : r)));
    const unit = mode === "line" ? "%" : "Rp";
    // Hitung berurutan: tiap tingkat memotong sisa dari tingkat sebelumnya.
    let remaining = base;
    const view = rows.map((r) => {
        const n = Number(r.value);
        const program = programs.find((p) => p.id === r.source);
        const tactical = r.source === TACTICAL;
        const okInt = /^\d+$/.test(r.value) && n >= 1;
        const max =
            mode === "line"
                ? Math.min(100, program?.max_percent ?? 100)
                : (program?.max_amount ?? remaining);
        const amount = okInt
            ? mode === "line"
                ? Math.round((remaining * n) / 100)
                : Math.min(n, remaining)
            : 0;
        const reason = r.choice === "Lainnya" ? r.other.trim() : r.choice;
        const budgetLeft = program
            ? program.budget_remaining - (usedElsewhere[program.id] ?? 0)
            : 0;
        const budgetAfter = program ? budgetLeft - amount : 0;
        let error = "";
        if (!tactical && !program) error = "Pilih sumber diskon.";
        else if (!okInt || n > max)
            error =
                mode === "line"
                    ? `Isi 1–${max}`
                    : `Isi 1–${money(Math.floor(max))}`;
        else if (tactical && reason.length < 3) error = "Alasan wajib.";
        else if (program && budgetAfter < 0) error = "Melebihi sisa budget.";
        else if (mode === "footer" && n > remaining)
            error = "Melebihi total order.";
        remaining -= amount;
        return {
            r,
            n,
            program,
            tactical,
            amount,
            reason,
            budgetLeft,
            budgetAfter,
            error,
        };
    });
    const programIds = view.filter((v) => v.program).map((v) => v.r.source);
    const duplicated = new Set(programIds).size !== programIds.length;
    const ok = !duplicated && view.every((v) => !v.error);
    const used = new Set(programIds);
    const available = programs.filter((p) => !used.has(p.id));
    const hasTactical = rows.some((r) => r.source === TACTICAL);
    function add() {
        const first = available[0];
        setRows((cur) => [
            ...cur,
            {
                source: first ? first.id : TACTICAL,
                value: "",
                choice: DISCOUNT_REASONS[0]!,
                other: "",
            },
        ]);
    }
    function apply() {
        const entries = view
            .slice()
            // Program lebih dulu, lalu pengajuan; urutan relatif tetap.
            .sort((a, b) => Number(a.tactical) - Number(b.tactical))
            .map((v) =>
                mode === "line"
                    ? v.tactical
                        ? { kind: "tactical", percent: v.n, reason: v.reason }
                        : {
                              kind: "program",
                              program_id: v.r.source,
                              percent: v.n,
                          }
                    : v.tactical
                      ? { kind: "tactical", amount: v.n, reason: v.reason }
                      : {
                            kind: "program",
                            program_id: v.r.source,
                            amount: v.n,
                        },
            );
        onApply(entries as T[]);
    }
    return (
        <BottomSheet title={title} onClose={onClose}>
            {mode === "footer" ? (
                <Callout tone="neu">
                    Setelah diskon baris: {money(base)}
                </Callout>
            ) : null}
            {view.map((v, i) => {
                const options = [
                    ...programs
                        .filter((p) => p.id === v.r.source || !used.has(p.id))
                        .map((p) => ({ value: p.id, label: p.name })),
                    ...(!hasTactical || v.tactical
                        ? [
                              {
                                  value: TACTICAL,
                                  label: "Tactical Discount (pengajuan)",
                              },
                          ]
                        : []),
                ];
                return (
                    <Card key={i} class="pos-disc">
                        <Select
                            label="Sumber diskon"
                            options={options}
                            value={v.r.source}
                            onChange={(source) => set(i, { source })}
                        />
                        {v.program && mode === "line" ? (
                            <span class="ui-row__sub">
                                Sisa budget {money(v.budgetLeft)} →{" "}
                                {money(Math.max(0, v.budgetAfter))}
                            </span>
                        ) : null}
                        {mode === "footer" && !v.tactical && !v.program ? (
                            <span class="ui-row__sub">
                                Program footer berjalan: tidak ada
                            </span>
                        ) : null}
                        <div class="pos-disc__val">
                            <Field
                                label={`Nilai (${unit})`}
                                type="text"
                                inputMode="numeric"
                                value={v.r.value}
                                onInput={(value) =>
                                    set(i, {
                                        value: value
                                            .replace(/\D/g, "")
                                            .slice(0, mode === "line" ? 3 : 12),
                                    })
                                }
                                error={
                                    v.r.value && v.error ? v.error : undefined
                                }
                            />
                            {v.tactical ? (
                                <Chip tone="warn">Perlu approval</Chip>
                            ) : v.amount ? (
                                <Chip tone="ok">−{money(v.amount)}</Chip>
                            ) : null}
                            <IconButton
                                icon="close"
                                label={`Hapus tingkat diskon ${i + 1}`}
                                onClick={() =>
                                    setRows((cur) =>
                                        cur.filter((_, j) => j !== i),
                                    )
                                }
                            />
                        </div>
                        {v.tactical ? (
                            <>
                                <Select
                                    label="Alasan (wajib)"
                                    options={DISCOUNT_REASONS.map((x) => ({
                                        value: x,
                                        label: x,
                                    }))}
                                    value={v.r.choice}
                                    onChange={(choice) => set(i, { choice })}
                                />
                                {v.r.choice === "Lainnya" ? (
                                    <Textarea
                                        label="Alasan pengajuan diskon"
                                        value={v.r.other}
                                        maxLength={500}
                                        onInput={(other) => set(i, { other })}
                                    />
                                ) : null}
                            </>
                        ) : null}
                    </Card>
                );
            })}
            {available.length || !hasTactical ? (
                <Button variant="sec" icon="plus" onClick={add}>
                    {mode === "line"
                        ? "Tambah diskon bertingkat"
                        : "Tambah diskon footer"}
                </Button>
            ) : null}
            {duplicated ? (
                <Callout tone="bad" alert>
                    Satu program hanya boleh sekali.
                </Callout>
            ) : null}
            <Button icon="check" disabled={!ok} onClick={apply}>
                {mode === "line"
                    ? "Terapkan diskon baris"
                    : "Terapkan diskon footer"}
            </Button>
            {initial.length ? (
                <Button variant="sec" onClick={() => onApply([])}>
                    Hapus semua diskon
                </Button>
            ) : null}
        </BottomSheet>
    );
}
