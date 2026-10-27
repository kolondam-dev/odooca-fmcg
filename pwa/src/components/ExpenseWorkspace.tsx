import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { z } from "zod";
import {
    ownerKey,
    type FieldProvider,
    type Identity,
} from "../domain/contracts";
import { ExpenseRequestSchema } from "../domain/expense";
import {
    ExpenseSimulation,
    realizationKey,
    settlementPreview,
    validateRealization,
} from "../domain/settlement";
import {
    LocalExpenseEvidenceSchema,
    type SimulatedAdvance,
} from "../domain/settlement-contracts";
import { fieldBusinessDate } from "../domain/morning";
import { money, queueLabels } from "../domain/format";
import type { FieldStore, QueueItem } from "../storage/store";
import type { Outbox } from "../domain/outbox";
import { EvidenceCapture } from "./Evidence";
import { Icon } from "./Icon";
const categories: Record<string, string> = {
    fuel_planned: "BBM terencana",
    fuel_emergency: "BBM insidentil",
    meal: "Uang makan luar kota",
    lodging: "Penginapan",
    repair: "Perbaikan darurat",
};
const approvers = (roles: string[]) =>
    roles
        .map((r) => (r === "supervisor" ? "Supervisor" : "Branch Manager"))
        .join(" + ");
const LineDraft = z
    .object({
        description: z.string(),
        amount: z.string(),
        merchant: z.string(),
        receipt_number: z.string(),
        expense_date: z.string(),
        evidence: LocalExpenseEvidenceSchema.optional(),
    })
    .strict();
const DraftSchema = z
    .object({
        lines: z.array(LineDraft).min(1).max(10),
        liters: z.string(),
        price: z.string(),
        beforeKm: z.string(),
        afterKm: z.string(),
        before: LocalExpenseEvidenceSchema.optional(),
        after: LocalExpenseEvidenceSchema.optional(),
    })
    .strict();
type Draft = z.infer<typeof DraftSchema>;
const line = () => ({
    description: "",
    amount: "",
    merchant: "",
    receipt_number: "",
    expense_date: fieldBusinessDate(),
});
const blank = (): Draft => ({
    lines: [line()],
    liters: "",
    price: "",
    beforeKm: "",
    afterKm: "",
});
export function ExpenseWorkspace({
    identity,
    provider,
    store,
    engine,
    queue,
    create,
    back,
    queued,
}: {
    identity: Identity;
    provider: FieldProvider;
    store: FieldStore;
    engine: Outbox;
    queue: QueueItem[];
    create: () => void;
    back: () => void;
    queued: () => void;
}) {
    const service = useMemo(
        () => new ExpenseSimulation(store, identity, provider, engine),
        [store, identity, provider, engine],
    );
    const [selected, setSelected] = useState<string>();
    const [advance, setAdvance] = useState<SimulatedAdvance>();
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const running = useRef(false);
    const requests = queue.filter(
        (q) => q.command.type === "field_expense.request",
    );
    const item = requests.find((q) => q.command.client_uuid === selected);
    const selectedRequest = item
        ? ExpenseRequestSchema.safeParse(item.command.payload)
        : undefined;
    const request = selectedRequest?.success ? selectedRequest.data : undefined;
    async function open(q: QueueItem) {
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        try {
            const a = await service.load(q.command.client_uuid);
            setAdvance(a);
            setSelected(q.command.client_uuid);
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Data biaya tidak tersedia.",
            );
        } finally {
            running.current = false;
            setBusy(false);
        }
    }
    async function disburse() {
        if (!selected || running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        try {
            setAdvance(await service.simulateDisbursement(selected));
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Simulasi pencairan gagal.",
            );
        } finally {
            running.current = false;
            setBusy(false);
        }
    }
    return (
        <>
            <button class="text-button" onClick={back}>
                <Icon name="caret" size={18} /> Kembali ke akun
            </button>
            <h1>Realisasi & uang lapangan</h1>
            <p class="notice">
                SIMULASI · Pengajuan, pencairan fiktif dan review realisasi
                adalah status berbeda. Tidak ada uang atau jurnal Odoo yang
                dibuat.
            </p>
            <button class="secondary full" onClick={create}>
                <Icon name="wallet" size={20} /> Ajukan uang lapangan baru
            </button>
            {error && (
                <p role="alert" class="form-error">
                    {error}
                </p>
            )}
            {!requests.length && (
                <p class="paper-card">
                    Belum ada pengajuan biaya pada akun ini.
                </p>
            )}
            <div class="list-stack expense-requests">
                {requests.map((q) => (
                    <button
                        class="card-row"
                        key={q.key}
                        disabled={busy}
                        onClick={() => void open(q)}
                        aria-pressed={selected === q.command.client_uuid}
                    >
                        <Icon name="receipt" />
                        <div>
                            <strong>{q.label}</strong>
                            <small>
                                {queueLabels[q.state]} ·{" "}
                                {q.command.client_uuid.slice(0, 8)}
                            </small>
                        </div>
                        <Icon name="caret" size={18} />
                    </button>
                ))}
            </div>
            {item && (
                <section class="paper-card">
                    <h2>Pengajuan terpilih</h2>
                    <p>
                        {request?.trip_id}
                        {request?.delivery_id
                            ? ` · ${request?.delivery_id}`
                            : ""}{" "}
                        ·{" "}
                        {categories[request?.category ?? ""] ??
                            "Biaya lapangan"}
                    </p>
                    {!advance ? (
                        <div class="demo-controls">
                            <p>
                                Penerimaan request bukan approval/pencairan.
                                Laboratorium berikut memakai persetujuan dan
                                uang muka fiktif untuk menguji form realisasi;
                                tidak memverifikasi bukti pengajuan.
                            </p>
                            <button
                                class="secondary full"
                                disabled={
                                    busy || item.state !== "needs_approval"
                                }
                                onClick={() => void disburse()}
                            >
                                Simulasikan approval & pencairan
                            </button>
                            <p class="footnote">
                                Hanya online + respons Normal. Limit contoh
                                simulator berasal dari policy fixture, bukan
                                limit perusahaan.
                            </p>
                        </div>
                    ) : (
                        <>
                            <p class="notice">
                                Uang muka fiktif {money(Number(advance.amount))}{" "}
                                · approval contoh:{" "}
                                {approvers(advance.approvals)} · limit contoh{" "}
                                {money(Number(advance.policy.supervisor_limit))}
                                .
                            </p>
                            <RealizationEditor
                                key={item.command.client_uuid}
                                item={item}
                                advance={advance}
                                owner={ownerKey(identity)}
                                store={store}
                                service={service}
                                queue={queue}
                                onSubmitted={async () => {
                                    setAdvance(
                                        await service.load(
                                            item.command.client_uuid,
                                        ),
                                    );
                                    queued();
                                }}
                            />
                        </>
                    )}
                </section>
            )}
        </>
    );
}
function RealizationEditor({
    item,
    advance,
    owner,
    store,
    service,
    queue,
    onSubmitted,
}: {
    item: QueueItem;
    advance: SimulatedAdvance;
    owner: string;
    store: FieldStore;
    service: ExpenseSimulation;
    queue: QueueItem[];
    onSubmitted: () => Promise<void>;
}) {
    const [draft, setDraft] = useState<Draft>(blank);
    const [loaded, setLoaded] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [saved, setSaved] = useState("");
    const running = useRef(false);
    const request = ExpenseRequestSchema.parse(item.command.payload);
    const fuel = request.category.startsWith("fuel");
    const locked = !!advance.realization_uuid;
    const receipt = queue.find(
        (q) => q.command.client_uuid === advance.realization_uuid,
    );
    const key = realizationKey(item.command.client_uuid);
    useEffect(() => {
        let active = true;
        setLoaded(false);
        void store
            .draft(owner, key)
            .then((value) => {
                if (!active) return;
                if (value !== undefined) {
                    const parsed = DraftSchema.safeParse(value);
                    if (!parsed.success) {
                        setError(
                            "Draft realisasi tidak valid. Data tetap disimpan; buat ulang setelah diperiksa.",
                        );
                        return;
                    }
                    setDraft(parsed.data);
                }
                setLoaded(true);
            })
            .catch(() => {
                if (active)
                    setError("Draft tidak dapat dibaca. Pengiriman ditahan.");
            });
        return () => {
            active = false;
        };
    }, [owner, key, store]);
    useEffect(() => {
        if (!loaded || locked) return;
        let active = true;
        setSaved("Menyimpan draft…");
        void store
            .draft(owner, key, draft)
            .then(() => {
                if (active) setSaved("Draft tersimpan di perangkat.");
            })
            .catch(() => {
                if (active) {
                    setSaved("");
                    setError(
                        "Draft gagal disimpan. Periksa ruang penyimpanan.",
                    );
                }
            });
        return () => {
            active = false;
        };
    }, [draft, loaded, locked, owner, key, store]);
    function payload() {
        return {
            source_request_uuid: item.command.client_uuid,
            advance_reference: advance.reference,
            lines: draft.lines,
            fuel: fuel
                ? {
                      liters: draft.liters,
                      price_per_liter: draft.price,
                      odometer_before:
                          draft.beforeKm.trim() === ""
                              ? null
                              : Number(draft.beforeKm),
                      odometer_after:
                          draft.afterKm.trim() === ""
                              ? null
                              : Number(draft.afterKm),
                      before: draft.before,
                      after: draft.after,
                  }
                : null,
            evidence_status: "local_map_pending",
        };
    }
    let preview: ReturnType<typeof settlementPreview> | undefined;
    try {
        const body = validateRealization(payload(), item, advance, owner);
        preview = settlementPreview(request, advance, body);
    } catch {
        /* Partial draft is expected while typing. */
    }
    async function send(e: SubmitEvent) {
        e.preventDefault();
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        try {
            await service.submit(item.command.client_uuid, payload());
            await onSubmitted();
        } catch (e) {
            setError(
                e instanceof Error
                    ? e.message
                    : "Realisasi gagal disimpan. Draft tetap tersedia.",
            );
        } finally {
            running.current = false;
            setBusy(false);
        }
    }
    const update = (n: number, patch: Partial<Draft["lines"][number]>) =>
        setDraft((d) => ({
            ...d,
            lines: d.lines.map((l, i) => (i === n ? { ...l, ...patch } : l)),
        }));
    return (
        <form class="realization-form" onSubmit={send}>
            <h2>Rincian realisasi</h2>
            <p class="footnote">
                Bukti harus tersimpan lokal dengan waktu/lokasi. Map masih
                pending; pengiriman berikut hanya ke simulator dan tidak
                meluluskan gate bukti resmi.
            </p>
            {locked && (
                <p class="notice" role="status">
                    {receipt ? queueLabels[receipt.state] : "Antrean tersimpan"}{" "}
                    · Realisasi dikunci setelah antre. Review, koreksi dan
                    settlement final menunggu backend; jangan membuat duplikat.
                </p>
            )}
            <fieldset
                disabled={!loaded || busy || locked}
                class="realization-fields"
            >
                {draft.lines.map((l, n) => (
                    <fieldset key={n} class="expense-line">
                        <legend>Komponen biaya {n + 1}</legend>
                        <label>
                            Uraian biaya {n + 1}
                            <input
                                required
                                maxLength={200}
                                value={l.description}
                                onInput={(e) =>
                                    update(n, {
                                        description: e.currentTarget.value,
                                    })
                                }
                            />
                        </label>
                        <label>
                            Nominal realisasi {n + 1} (Rp)
                            <input
                                required
                                type="number"
                                min="1"
                                max="100000000"
                                step="1"
                                inputMode="numeric"
                                value={l.amount}
                                onInput={(e) =>
                                    update(n, { amount: e.currentTarget.value })
                                }
                            />
                        </label>
                        <label>
                            Nama penjual {n + 1}
                            <input
                                required
                                maxLength={100}
                                value={l.merchant}
                                onInput={(e) =>
                                    update(n, {
                                        merchant: e.currentTarget.value,
                                    })
                                }
                            />
                        </label>
                        <label>
                            Nomor struk {n + 1}
                            <input
                                required
                                maxLength={100}
                                value={l.receipt_number}
                                onInput={(e) =>
                                    update(n, {
                                        receipt_number: e.currentTarget.value,
                                    })
                                }
                            />
                        </label>
                        <label>
                            Tanggal struk {n + 1}
                            <input
                                type="date"
                                required
                                value={l.expense_date}
                                onInput={(e) =>
                                    update(n, {
                                        expense_date: e.currentTarget.value,
                                    })
                                }
                            />
                        </label>
                        <fieldset class="evidence-group">
                            <legend>Foto struk {n + 1}</legend>
                            <EvidenceCapture
                                store={store}
                                owner={owner}
                                existingRef={l.evidence}
                                onChange={(ref) => update(n, { evidence: ref })}
                            />
                            {l.evidence && (
                                <p class="footnote">
                                    Bukti lokal tersimpan ·{" "}
                                    {l.evidence.id.slice(0, 8)} · map pending
                                </p>
                            )}
                        </fieldset>
                        {!fuel && draft.lines.length > 1 && (
                            <button
                                type="button"
                                class="text-button"
                                onClick={() =>
                                    setDraft((d) => ({
                                        ...d,
                                        lines: d.lines.filter(
                                            (_, i) => i !== n,
                                        ),
                                    }))
                                }
                            >
                                Hapus komponen {n + 1}
                            </button>
                        )}
                    </fieldset>
                ))}
                {!fuel && draft.lines.length < 10 && (
                    <button
                        type="button"
                        class="secondary full"
                        onClick={() =>
                            setDraft((d) => ({
                                ...d,
                                lines: [...d.lines, line()],
                            }))
                        }
                    >
                        Tambah komponen biaya
                    </button>
                )}
                {fuel && (
                    <fieldset class="expense-line">
                        <legend>Pengisian BBM</legend>
                        <label>
                            Liter BBM
                            <input
                                required
                                inputMode="decimal"
                                value={draft.liters}
                                onInput={(e) =>
                                    setDraft((d) => ({
                                        ...d,
                                        liters: e.currentTarget.value,
                                    }))
                                }
                            />
                        </label>
                        <label>
                            Harga per liter (Rp)
                            <input
                                required
                                type="number"
                                min="1"
                                step="1"
                                value={draft.price}
                                onInput={(e) =>
                                    setDraft((d) => ({
                                        ...d,
                                        price: e.currentTarget.value,
                                    }))
                                }
                            />
                        </label>
                        <label>
                            KM sebelum pengisian
                            <input
                                required
                                type="number"
                                min="0"
                                step="1"
                                value={draft.beforeKm}
                                onInput={(e) =>
                                    setDraft((d) => ({
                                        ...d,
                                        beforeKm: e.currentTarget.value,
                                    }))
                                }
                            />
                        </label>
                        <label>
                            KM setelah pengisian
                            <input
                                required
                                type="number"
                                min="0"
                                step="1"
                                value={draft.afterKm}
                                onInput={(e) =>
                                    setDraft((d) => ({
                                        ...d,
                                        afterKm: e.currentTarget.value,
                                    }))
                                }
                            />
                        </label>
                        <fieldset class="evidence-group">
                            <legend>Foto odometer sebelum</legend>
                            <EvidenceCapture
                                store={store}
                                owner={owner}
                                existingRef={draft.before}
                                onChange={(ref) =>
                                    setDraft((d) => ({ ...d, before: ref }))
                                }
                            />
                            {draft.before && (
                                <p class="footnote">
                                    Bukti lokal tersimpan · map pending
                                </p>
                            )}
                        </fieldset>
                        <fieldset class="evidence-group">
                            <legend>Foto odometer sesudah</legend>
                            <EvidenceCapture
                                store={store}
                                owner={owner}
                                existingRef={draft.after}
                                onChange={(ref) =>
                                    setDraft((d) => ({ ...d, after: ref }))
                                }
                            />
                            {draft.after && (
                                <p class="footnote">
                                    Bukti lokal tersimpan · map pending
                                </p>
                            )}
                        </fieldset>
                    </fieldset>
                )}
            </fieldset>
            {preview && (
                <section
                    class="settlement-preview"
                    aria-label="Estimasi settlement"
                >
                    <h3>Estimasi settlement</h3>
                    <dl>
                        <dt>Uang muka fiktif</dt>
                        <dd>{money(Number(advance.amount))}</dd>
                        <dt>Total realisasi</dt>
                        <dd>{money(preview.total)}</dd>
                        <dt>Perlu pengembalian</dt>
                        <dd>{money(preview.refund)}</dd>
                        <dt>Perlu tambahan / variance</dt>
                        <dd>{money(preview.variance)}</dd>
                    </dl>
                    <p>
                        Routing review contoh: {approvers(preview.approvals)}.
                        Berdasarkan total exposure, bukan hanya selisih.
                    </p>
                    <p class="footnote">
                        Saldo belum final. Pengembalian belum diterima dan
                        tambahan belum disetujui/dicairkan.
                    </p>
                </section>
            )}
            {error && (
                <p role="alert" class="form-error">
                    {error}
                </p>
            )}
            {!locked && (
                <>
                    <p role="status" class="footnote">
                        {saved}
                    </p>
                    <button
                        class="primary full"
                        disabled={!loaded || busy}
                        type="submit"
                    >
                        {busy
                            ? "Menyimpan…"
                            : "Simpan realisasi ke antrean demo"}
                    </button>
                </>
            )}
        </form>
    );
}
