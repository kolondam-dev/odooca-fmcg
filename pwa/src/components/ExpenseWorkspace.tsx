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
import { businessRejected } from "../domain/outbox-state";
import { fieldBusinessDate } from "../domain/morning";
import { money, queueLabels } from "../domain/format";
import type { FieldStore, QueueItem } from "../storage/store";
import type { Outbox } from "../domain/outbox";
import { EvidenceCapture } from "./Evidence";
import {
    Button,
    Callout,
    Card,
    Field,
    ListRow,
    Screen,
    ScreenHeader,
    Textarea,
} from "../ui";
const categories: Record<string, string> = {
    fuel: "BBM",
    emergency: "Darurat",
    fuel_planned: "BBM terencana",
    fuel_emergency: "BBM insidentil",
    meal: "Makan",
    lodging: "Nginap",
    repair: "Perbaikan darurat",
    delivery_fee: "Biaya pengiriman / toko",
};
const approvers = (roles: string[]) =>
    roles
        .map((r) => (r === "supervisor" ? "Supervisor" : "Branch Manager"))
        .join(" + ");
const LineDraft = z
    .object({
        id: z
            .string()
            .uuid()
            .default(() => crypto.randomUUID()),
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
        correctionReason: z.string().max(500).default(""),
        lines: z.array(LineDraft).min(1).max(10),
        liters: z.string(),
        price: z.string(),
        beforeKm: z.string(),
        afterKm: z.string(),
        before: LocalExpenseEvidenceSchema.optional(),
        after: LocalExpenseEvidenceSchema.optional(),
    })
    .strict()
    .refine((d) => new Set(d.lines.map((l) => l.id)).size === d.lines.length);
type Draft = z.infer<typeof DraftSchema>;
const line = () => ({
    id: crypto.randomUUID(),
    description: "",
    amount: "",
    merchant: "",
    receipt_number: "",
    expense_date: fieldBusinessDate(),
});
const blank = (): Draft => ({
    correctionReason: "",
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
            setError(e instanceof Error ? e.message : "Pencairan gagal.");
        } finally {
            running.current = false;
            setBusy(false);
        }
    }
    const [advances, setAdvances] = useState<Record<string, SimulatedAdvance>>(
        {},
    );
    useEffect(() => {
        let active = true;
        void Promise.all(
            requests.map(async (q) => {
                try {
                    const a = await service.load(q.command.client_uuid);
                    return a
                        ? ([q.command.client_uuid, a] as const)
                        : undefined;
                } catch {
                    return undefined;
                }
            }),
        ).then((rows) => {
            if (active)
                setAdvances(
                    Object.fromEntries(rows.filter((r) => r !== undefined)),
                );
        });
        return () => {
            active = false;
        };
    }, [service, queue.length, advance]);
    // Saldo = uang muka yang sudah cair dan belum direalisasi.
    const saldo = Object.values(advances)
        .filter((a) => !a.realization_uuid)
        .reduce((n, a) => n + Number(a.amount), 0);
    const statusOf = (q: QueueItem) => {
        const a = advances[q.command.client_uuid];
        if (q.state === "rejected")
            return { tone: "bad", label: "Ditolak" } as const;
        if (a?.realization_uuid)
            return { tone: "info", label: "Direalisasi" } as const;
        if (a) return { tone: "ok", label: "Disetujui" } as const;
        return { tone: "warn", label: "Menunggu" } as const;
    };
    if (item) {
        return (
            <Screen
                label="Realisasi uang lapangan"
                class="ui-screen--over"
                header={
                    <ScreenHeader
                        title="Realisasi uang lapangan"
                        onBack={() => {
                            setSelected(undefined);
                            setAdvance(undefined);
                        }}
                    />
                }
            >
                <Card>
                    <ListRow
                        icon="wallet"
                        title={
                            categories[request?.category ?? ""] ??
                            "Biaya lapangan"
                        }
                        sub={`${request?.trip_id ?? ""}${request?.delivery_id ? ` · ${request.delivery_id}` : ""} · ${money(Number(request?.amount ?? 0))}`}
                        status={statusOf(item)}
                    />
                </Card>
                {error ? (
                    <Callout tone="bad" alert>
                        {error}
                    </Callout>
                ) : null}
                {!advance ? (
                    __QA_TOOLS__ ? (
                        <Card>
                            <Callout tone="info">
                                Penerimaan request bukan approval/pencairan.
                                Laboratorium berikut memakai persetujuan dan
                                uang muka fiktif untuk menguji form realisasi.
                            </Callout>
                            <Button
                                variant="sec"
                                disabled={
                                    busy || item.state !== "needs_approval"
                                }
                                onClick={() => void disburse()}
                            >
                                Proses approval & pencairan
                            </Button>
                        </Card>
                    ) : (
                        <Callout tone="neu">
                            <span role="status">
                                Menunggu approval dan pencairan.
                            </span>
                        </Callout>
                    )
                ) : (
                    <>
                        <Callout tone="info">
                            Uang muka fiktif {money(Number(advance.amount))} ·
                            approval contoh: {approvers(advance.approvals)} ·
                            limit contoh{" "}
                            {money(Number(advance.policy.supervisor_limit))}.
                        </Callout>
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
            </Screen>
        );
    }
    return (
        <Screen
            label="Uang lapangan"
            class="ui-screen--over"
            header={<ScreenHeader title="Uang lapangan" onBack={back} />}
        >
            <Card>
                <div class="exp-saldo">
                    <div>
                        <span class="exp-saldo__label">Saldo</span>
                        <strong class="exp-saldo__amt">{money(saldo)}</strong>
                    </div>
                    <Button size="md" icon="plus" onClick={create}>
                        Ajukan
                    </Button>
                </div>
            </Card>
            <h2 class="ui-section">Pengajuan & realisasi</h2>
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
            {requests.length ? (
                <Card>
                    {requests.map((q, i) => {
                        const p = ExpenseRequestSchema.safeParse(
                            q.command.payload,
                        );
                        return (
                            <ListRow
                                key={q.key}
                                divider={i > 0}
                                title={
                                    p.success
                                        ? (categories[p.data.category] ??
                                          q.label)
                                        : q.label
                                }
                                sub={`${p.success ? dayMonth(p.data.scheduled_date) : ""} · ${p.success ? money(Number(p.data.amount)) : ""}`}
                                status={statusOf(q)}
                                disabled={busy}
                                onClick={() => void open(q)}
                            />
                        );
                    })}
                </Card>
            ) : (
                <Callout tone="neu">
                    Belum ada pengajuan biaya pada akun ini.
                </Callout>
            )}
        </Screen>
    );
}
const dayMonth = (iso: string) =>
    new Intl.DateTimeFormat("id-ID", {
        day: "numeric",
        month: "short",
        timeZone: "UTC",
    }).format(new Date(`${iso}T00:00:00Z`));
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
    const receipt = queue.find(
        (q) => q.command.client_uuid === advance.realization_uuid,
    );
    const correcting = !!advance.realization_uuid && businessRejected(receipt);
    const locked = !!advance.realization_uuid && !correcting;
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
            lines: draft.lines.map(({ id, ...value }) => {
                void id;
                return value;
            }),
            ...(correcting
                ? {
                      supersedes_uuid: advance.realization_uuid!,
                      correction_reason: draft.correctionReason,
                  }
                : {}),
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
    const history = queue.filter(
        (q) =>
            q.command.type === "field_expense.realization.submit" &&
            q.command.payload.source_request_uuid === item.command.client_uuid,
    );
    const frozen = !loaded || busy || locked;
    const num = (v: string) => v.replace(/[^\d.]/g, "");
    return (
        <form class="exp-form" onSubmit={send}>
            <h2 class="ui-section">
                {correcting ? "Koreksi realisasi ditolak" : "Rincian realisasi"}
            </h2>
            {correcting && (
                <Callout tone="warn">
                    Receipt penolakan bisnis diterima. Koreksi memakai UUID
                    baru; versi ditolak tetap tersimpan.{" "}
                    {receipt?.receipt?.message}
                </Callout>
            )}
            <div role="region" aria-label="Riwayat realisasi">
                {history.length ? (
                    <Card>
                        {history.map((q, i) => (
                            <ListRow
                                key={q.key}
                                divider={i > 0}
                                title={`${q.command.client_uuid.slice(0, 8)} · ${queueLabels[q.state]}${
                                    q.command.type ===
                                        "field_expense.realization.submit" &&
                                    q.command.payload.supersedes_uuid
                                        ? ` · koreksi ${q.command.payload.supersedes_uuid.slice(0, 8)}`
                                        : ""
                                }`}
                                sub={[
                                    q.receipt?.message,
                                    q.command.type ===
                                        "field_expense.realization.submit" &&
                                    q.command.payload.correction_reason
                                        ? `Alasan koreksi: ${q.command.payload.correction_reason}`
                                        : undefined,
                                ]
                                    .filter(Boolean)
                                    .join(" · ")}
                            />
                        ))}
                    </Card>
                ) : null}
            </div>
            <p class="ev__note">
                Bukti harus tersimpan lokal dengan waktu/lokasi. Map masih
                pending; pengiriman berikut hanya ke simulator dan tidak
                meluluskan gate bukti resmi.
            </p>
            {locked && (
                <div role="status">
                    <Callout tone="info">
                        {receipt
                            ? queueLabels[receipt.state]
                            : "Antrean tersimpan"}{" "}
                        · Realisasi dikunci setelah antre. Koreksi hanya untuk
                        receipt penolakan bisnis; settlement final menunggu
                        backend. Jangan membuat duplikat.
                    </Callout>
                </div>
            )}
            {correcting && (
                <Textarea
                    label="Alasan koreksi"
                    required
                    disabled={frozen}
                    minLength={5}
                    maxLength={500}
                    value={draft.correctionReason}
                    onInput={(v) =>
                        setDraft((d) => ({ ...d, correctionReason: v }))
                    }
                />
            )}
            {draft.lines.map((l, n) => (
                <fieldset key={l.id} class="exp-line" disabled={frozen}>
                    <legend>Komponen biaya {n + 1}</legend>
                    <Field
                        label={`Uraian biaya ${n + 1}`}
                        required
                        maxLength={200}
                        value={l.description}
                        onInput={(v) => update(n, { description: v })}
                    />
                    <Field
                        label={`Nominal realisasi ${n + 1} (Rp)`}
                        required
                        inputMode="numeric"
                        maxLength={9}
                        value={l.amount}
                        onInput={(v) =>
                            update(n, { amount: v.replace(/\D/g, "") })
                        }
                    />
                    <Field
                        label={`Nama penjual ${n + 1}`}
                        required
                        maxLength={100}
                        value={l.merchant}
                        onInput={(v) => update(n, { merchant: v })}
                    />
                    <Field
                        label={`Nomor struk ${n + 1}`}
                        required
                        maxLength={100}
                        value={l.receipt_number}
                        onInput={(v) => update(n, { receipt_number: v })}
                    />
                    <Field
                        label={`Tanggal struk ${n + 1}`}
                        type="date"
                        required
                        value={l.expense_date}
                        onInput={(v) => update(n, { expense_date: v })}
                    />
                    <fieldset class="evidence-group">
                        <legend>Foto struk {n + 1}</legend>
                        <EvidenceCapture
                            store={store}
                            owner={owner}
                            existingRef={l.evidence}
                            onChange={(ref) => update(n, { evidence: ref })}
                        />
                        {l.evidence && (
                            <p class="ev__note">
                                Bukti lokal tersimpan ·{" "}
                                {l.evidence.id.slice(0, 8)} · map pending
                            </p>
                        )}
                    </fieldset>
                    {!fuel && draft.lines.length > 1 && (
                        <Button
                            variant="sec"
                            size="sm"
                            onClick={() =>
                                setDraft((d) => ({
                                    ...d,
                                    lines: d.lines.filter((_, i) => i !== n),
                                }))
                            }
                        >
                            Hapus komponen {n + 1}
                        </Button>
                    )}
                </fieldset>
            ))}
            {!fuel && draft.lines.length < 10 && (
                <Button
                    variant="sec"
                    size="md"
                    icon="plus"
                    disabled={frozen}
                    onClick={() =>
                        setDraft((d) => ({ ...d, lines: [...d.lines, line()] }))
                    }
                >
                    Tambah komponen biaya
                </Button>
            )}
            {fuel && (
                <fieldset class="exp-line" disabled={frozen}>
                    <legend>Pengisian BBM</legend>
                    <Field
                        label="Liter BBM"
                        required
                        inputMode="decimal"
                        value={draft.liters}
                        onInput={(v) =>
                            setDraft((d) => ({ ...d, liters: num(v) }))
                        }
                    />
                    <Field
                        label="Harga per liter (Rp)"
                        required
                        inputMode="numeric"
                        value={draft.price}
                        onInput={(v) =>
                            setDraft((d) => ({
                                ...d,
                                price: v.replace(/\D/g, ""),
                            }))
                        }
                    />
                    <Field
                        label="KM sebelum pengisian"
                        required
                        inputMode="numeric"
                        value={draft.beforeKm}
                        onInput={(v) =>
                            setDraft((d) => ({
                                ...d,
                                beforeKm: v.replace(/\D/g, ""),
                            }))
                        }
                    />
                    <Field
                        label="KM setelah pengisian"
                        required
                        inputMode="numeric"
                        value={draft.afterKm}
                        onInput={(v) =>
                            setDraft((d) => ({
                                ...d,
                                afterKm: v.replace(/\D/g, ""),
                            }))
                        }
                    />
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
                            <p class="ev__note">
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
                            <p class="ev__note">
                                Bukti lokal tersimpan · map pending
                            </p>
                        )}
                    </fieldset>
                </fieldset>
            )}
            {preview && (
                <section aria-label="Estimasi settlement">
                    <Card>
                        <h3 class="ui-section">Estimasi settlement</h3>
                        <dl class="exp-dl">
                            <dt>Uang muka fiktif</dt>
                            <dd>{money(Number(advance.amount))}</dd>
                            <dt>Total realisasi</dt>
                            <dd>{money(preview.total)}</dd>
                            <dt>Perlu pengembalian</dt>
                            <dd>{money(preview.refund)}</dd>
                            <dt>Perlu tambahan / variance</dt>
                            <dd>{money(preview.variance)}</dd>
                        </dl>
                        <p class="ev__note">
                            Routing review contoh:{" "}
                            {approvers(preview.approvals)}. Berdasarkan total
                            exposure, bukan hanya selisih. Saldo belum final.
                            Pengembalian belum diterima dan tambahan belum
                            disetujui/dicairkan.
                        </p>
                    </Card>
                </section>
            )}
            {error && (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            )}
            {!locked && (
                <>
                    <p role="status" class="ev__note">
                        {saved}
                    </p>
                    <Button
                        type="submit"
                        icon="check"
                        disabled={!loaded || busy}
                    >
                        {busy ? "Menyimpan…" : "Simpan realisasi ke antrean"}
                    </Button>
                </>
            )}
        </form>
    );
}
