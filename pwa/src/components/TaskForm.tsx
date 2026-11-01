import { useEffect, useRef, useState } from "preact/hooks";
import type { Dialog } from "../ui/navigation";
import { useDialog } from "../ui/useDialog";
import { ExpenseContextFields } from "./ExpenseContextFields";
import { LocalDateInput } from "./LocalDateInput";
import { AttendanceCapture } from "./AttendanceCapture";
import { Icon } from "./Icon";
import { OrderCatalog, OrderSummary } from "./OrderSheet";
import { DisplayPhoto } from "./DisplayPhoto";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";
import { orderQuote, type OrderUom } from "../domain/order-pricing";
import {
    validateOrder,
    type Command,
    type Identity,
    type Snapshot,
} from "../domain/contracts";
import { validateExpense } from "../domain/expense";
import { money } from "../domain/format";
import type { FieldStore, QueueItem } from "../storage/store";
export function TaskForm({
    dialog,
    identity,
    snapshot,
    owner,
    submit,
    startSession,
    close,
    workStatus,
    store,
}: {
    workStatus: string;
    store: FieldStore;
    dialog: Dialog;
    identity: Identity;
    snapshot: Snapshot;
    owner: string;
    submit: (
        type: Command["type"],
        payload: Record<string, unknown>,
        label: string,
    ) => Promise<QueueItem>;
    startSession: (
        event: "check_in" | "check_out",
        evidence: EvidenceRef,
    ) => Promise<void>;
    close: () => void;
}) {
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [orderPreview, setOrderPreview] = useState(false);
    const dialogRef = useDialog(() => {
        if (!busy) close();
    });
    const [qty, setQty] = useState<Record<string, number>>({});
    const [principal, setPrincipal] = useState(
        () => snapshot.products[0]?.principal ?? "mayora",
    );
    const [units, setUnits] = useState<Record<string, OrderUom>>({});
    const [discount, setDiscount] = useState(0);
    const [discountReason, setDiscountReason] = useState("");
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [restored, setRestored] = useState(false);
    const [category, setCategory] = useState("fuel_planned");
    const busyRef = useRef(false);
    busyRef.current = busy;
    const key = dialog.type === "order" ? `order:${dialog.outlet}` : "";
    useEffect(() => {
        if (!key) {
            setRestored(true);
            return;
        }
        let active = true;
        void store
            .draft(owner, key)
            .then((value) => {
                if (active && value && typeof value === "object") {
                    const v = value as {
                        quantities: Record<string, number>;
                        principal: string;
                        units?: Record<string, OrderUom>;
                        discount?: number;
                        discountReason?: string;
                        evidence?: EvidenceRef;
                    };
                    setQty(v.quantities ?? {});
                    setPrincipal(v.principal ?? "mayora");
                    setUnits(v.units ?? {});
                    setDiscount(v.discount ?? 0);
                    setDiscountReason(v.discountReason ?? "");
                    if (v.evidence) setEvidence(v.evidence);
                }
                if (active) setRestored(true);
            })
            .catch(() => {
                setError("Draft tidak dapat dibaca.");
            });
        return () => {
            active = false;
        };
    }, []);
    useEffect(() => {
        if (restored && key)
            void store
                .draft(owner, key, {
                    quantities: qty,
                    principal,
                    units,
                    discount,
                    discountReason,
                    ...(evidence ? { evidence } : {}),
                })
                .catch(() =>
                    setError("Draft gagal disimpan. Periksa penyimpanan."),
                );
    }, [qty, principal, units, discount, discountReason, evidence, restored]);
    const orderLines = Object.entries(qty).filter(([, q]) => q > 0);
    const title = {
        order: "Buat Sales Order",
        extra: "Ajukan extra call",
        proof: "Bukti pengiriman",
        expense: "Uang lapangan",
        attendance: "Absensi foto & lokasi",
        leave: "Pengajuan cuti",
        profile: "Profil & Sesi Akun",
    }[dialog.type];
    async function send(e: SubmitEvent) {
        e.preventDefault();
        if (busy) return;
        if (dialog.type === "order" && !orderPreview) {
            if (orderLines.length && evidence) setOrderPreview(true);
            else setError("Lengkapi item dan foto display sebelum preview.");
            return;
        }
        setError("");
        const f = new FormData(e.currentTarget as HTMLFormElement);
        setBusy(true);
        try {
            let type: Command["type"];
            let payload: Record<string, unknown>;
            let label: string;
            if (dialog.type === "order") {
                if (!evidence)
                    throw new Error(
                        "Ambil foto display outlet sebelum mengirim order.",
                    );
                const lines = Object.entries(qty)
                    .filter(([, q]) => q > 0)
                    .map(([productId, quantity]) => ({ productId, quantity }));
                const invalid = validateOrder(lines, snapshot);
                if (invalid) throw new Error(invalid);
                type = "sales.order.submit";
                payload = {
                    outlet_id: dialog.outlet,
                    snapshot_version: snapshot.version,
                    lines: lines.map((l) => ({
                        product_id: l.productId,
                        qty: String(l.quantity),
                        uom: units[l.productId] ?? "carton",
                    })),
                    pricing_version: 1,
                    ...(discount > 0
                        ? {
                              discount_request: {
                                  percent: discount,
                                  reason: discountReason,
                              },
                          }
                        : {}),
                    note: String(f.get("note") ?? ""),
                    observed_total: String(
                        orderQuote(
                            lines.map((l) => ({
                                product_id: l.productId,
                                qty: String(l.quantity),
                                uom: units[l.productId] ?? "carton",
                            })),
                            snapshot,
                            discount > 0
                                ? { percent: discount, reason: discountReason }
                                : undefined,
                        ).requestedTotal,
                    ),
                };
                label = `Order • ${snapshot.outlets.find((o) => o.id === dialog.outlet)?.name}`;
            } else if (dialog.type === "extra") {
                type = "sales.extra_call.request";
                payload = {
                    outlet_name: f.get("outlet"),
                    reason: f.get("reason"),
                };
                label = `Extra call • ${f.get("outlet")}`;
            } else if (dialog.type === "expense") {
                const amount = Number(f.get("amount"));
                if (!Number.isFinite(amount) || amount < 1)
                    throw new Error("Nominal harus lebih dari nol.");
                type = "field_expense.request";
                payload = validateExpense(
                    {
                        category,
                        amount: String(amount),
                        trip_id: String(f.get("trip") ?? ""),
                        delivery_id:
                            f.get("scope") === "delivery"
                                ? String(f.get("delivery") ?? "").trim() || null
                                : null,
                        expense_scope: f.get("scope"),
                        scheduled_date: f.get("date"),
                        odometer:
                            f.get("odometer") === null ||
                            f.get("odometer") === ""
                                ? null
                                : Number(f.get("odometer")),
                        reason: f.get("reason"),
                        evidence: evidence ?? null,
                    },
                    identity.businessDate,
                );
                label = `Petty cash • ${money(amount)}`;
            } else if (dialog.type === "leave") {
                const from = String(f.get("from")),
                    to = String(f.get("to"));
                if (to < from)
                    throw new Error(
                        "Tanggal selesai tidak boleh sebelum mulai.",
                    );
                type = "hris.leave.request";
                payload = {
                    date_from: from,
                    date_to: to,
                    reason: f.get("reason"),
                };
                label = "Pengajuan cuti";
            } else {
                if (!evidence)
                    throw new Error("Simpan foto dan lokasi dahulu.");
                if (dialog.type === "attendance") {
                    await startSession(dialog.event ?? "check_in", evidence);
                    close();
                    return;
                }
                if (dialog.type !== "proof")
                    throw new Error("Form bukti tidak dikenal.");
                type = "delivery.proof.submit";
                payload = {
                    event: f.get("event"),
                    delivery_id: dialog.delivery,
                    result: f.get("result"),
                    evidence,
                    map_status: "pending",
                };
                label = `POD • ${dialog.delivery}`;
            }
            // Evidence remains local: receipts must not claim the backend has verified it.
            if (
                evidence &&
                ["hris.attendance.capture", "delivery.proof.submit"].includes(
                    type,
                )
            )
                throw new Error(
                    "Bukti tersimpan lokal. Pengiriman resmi menunggu API evidence & snapshot peta.",
                );
            await submit(type, payload, label);
            if (key) await store.removeDraft(owner, key);
        } catch (x) {
            setError(
                x instanceof Error
                    ? x.message
                    : "Penyimpanan gagal. Form tetap tersedia.",
            );
        } finally {
            setBusy(false);
        }
    }
    return (
        <div class="modal-backdrop page-backdrop">
            <section
                ref={dialogRef}
                class="sheet full-page-form"
                role="dialog"
                aria-modal="true"
                aria-labelledby="dialog-title"
            >
                <header class="sheet-head">
                    <div>
                        <p class="eyebrow">{identity.name}</p>
                        <h2 id="dialog-title">{title}</h2>
                    </div>
                    <button
                        class="icon-button"
                        type="button"
                        onClick={close}
                        aria-label="Tutup form"
                        disabled={busy}
                    >
                        <Icon name="close" />
                    </button>
                </header>
                <form onSubmit={(e) => void send(e)}>
                    <div class="sheet-body">
                        {dialog.type === "order" && (
                            <>
                                <nav
                                    class="workflow-tabs"
                                    aria-label="Tahap order"
                                >
                                    <button
                                        type="button"
                                        aria-pressed={!orderPreview}
                                        onClick={() => setOrderPreview(false)}
                                    >
                                        Produk & cart
                                    </button>
                                    <button
                                        type="button"
                                        aria-pressed={orderPreview}
                                        disabled={
                                            !orderLines.length || !evidence
                                        }
                                        onClick={() => setOrderPreview(true)}
                                    >
                                        Preview order
                                    </button>
                                </nav>
                                {orderPreview && (
                                    <section
                                        class="order-preview"
                                        aria-label="Preview order"
                                    >
                                        <h3>
                                            {
                                                snapshot.outlets.find(
                                                    (o) =>
                                                        o.id === dialog.outlet,
                                                )?.name
                                            }
                                        </h3>
                                        {orderLines.map(([id, quantity]) => (
                                            <div class="preview-line" key={id}>
                                                <span>
                                                    {
                                                        snapshot.products.find(
                                                            (p) => p.id === id,
                                                        )?.name
                                                    }
                                                    <small>
                                                        {quantity}{" "}
                                                        {units[id] ?? "carton"}
                                                    </small>
                                                </span>
                                                <button
                                                    type="button"
                                                    class="secondary"
                                                    aria-label={`Hapus ${snapshot.products.find((p) => p.id === id)?.name}`}
                                                    onClick={() =>
                                                        setQty({
                                                            ...qty,
                                                            [id]: 0,
                                                        })
                                                    }
                                                >
                                                    Hapus
                                                </button>
                                            </div>
                                        ))}
                                        <p>
                                            {discount > 0
                                                ? `Diskon ${discount}% • menunggu approval`
                                                : "Harga sesuai snapshot"}
                                        </p>
                                    </section>
                                )}
                                <div hidden={orderPreview}>
                                    <p class="sheet-subtitle">
                                        {
                                            snapshot.outlets.find(
                                                (o) => o.id === dialog.outlet,
                                            )?.name
                                        }{" "}
                                        · satu principal per order
                                    </p>
                                    <DisplayPhoto
                                        store={store}
                                        owner={owner}
                                        value={evidence}
                                        outletName={
                                            snapshot.outlets.find(
                                                (o) => o.id === dialog.outlet,
                                            )?.name ?? "Outlet"
                                        }
                                        coordinates={(() => {
                                            const outlet =
                                                snapshot.outlets.find(
                                                    (o) =>
                                                        o.id === dialog.outlet,
                                                );
                                            return outlet
                                                ? {
                                                      latitude: outlet.latitude,
                                                      longitude:
                                                          outlet.longitude,
                                                  }
                                                : undefined;
                                        })()}
                                        onChange={setEvidence}
                                    />
                                    <OrderCatalog
                                        snapshot={snapshot}
                                        principal={principal}
                                        onPrincipal={setPrincipal}
                                        qty={qty}
                                        onQty={setQty}
                                        units={units}
                                        onUnits={setUnits}
                                    />
                                    <details class="order-extra">
                                        <summary>Catatan & diskon</summary>
                                        <label>
                                            Diskon diminta (%)
                                            <input
                                                aria-label="Diskon diminta (%)"
                                                type="number"
                                                min="0"
                                                max="100"
                                                step="1"
                                                inputMode="numeric"
                                                value={discount}
                                                onInput={(e) =>
                                                    setDiscount(
                                                        Number(
                                                            e.currentTarget
                                                                .value,
                                                        ),
                                                    )
                                                }
                                            />
                                        </label>
                                        {discount > 0 && (
                                            <label>
                                                Alasan permintaan diskon
                                                <textarea
                                                    required
                                                    minLength={3}
                                                    maxLength={500}
                                                    value={discountReason}
                                                    onInput={(e) =>
                                                        setDiscountReason(
                                                            e.currentTarget
                                                                .value,
                                                        )
                                                    }
                                                />
                                            </label>
                                        )}
                                        <label>
                                            Catatan order
                                            <textarea
                                                name="note"
                                                maxLength={500}
                                                placeholder="Permintaan outlet (opsional)"
                                            />
                                        </label>
                                    </details>
                                </div>
                            </>
                        )}
                        {dialog.type === "extra" && (
                            <>
                                <p class="notice">
                                    Kunjungan di luar PJP baru sah setelah
                                    supervisor menyetujui.
                                </p>
                                <label>
                                    Nama outlet
                                    <input
                                        name="outlet"
                                        required
                                        maxLength={100}
                                    />
                                </label>
                                <label>
                                    Alasan extra call
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                            </>
                        )}
                        {dialog.type === "expense" && (
                            <>
                                <label>
                                    Kategori
                                    <select
                                        aria-label="Kategori"
                                        value={category}
                                        onChange={(e) =>
                                            setCategory(e.currentTarget.value)
                                        }
                                    >
                                        <option value="fuel_planned">
                                            BBM terencana (H-1)
                                        </option>
                                        <option value="fuel_emergency">
                                            BBM insidentil
                                        </option>
                                        <option value="meal">
                                            Uang makan luar kota
                                        </option>
                                        <option value="lodging">
                                            Penginapan luar kota
                                        </option>
                                        <option value="repair">
                                            Perbaikan darurat / derek
                                        </option>
                                    </select>
                                </label>
                                <ExpenseContextFields
                                    deliveries={snapshot.deliveries}
                                    trip={dialog.trip}
                                />
                                <p class="notice">
                                    {category === "fuel_emergency"
                                        ? "BBM insidentil: Supervisor + Branch Manager, berapa pun nominalnya."
                                        : "Wajib approval supervisor. Di atas limit kewenangan diteruskan ke Branch Manager."}
                                </p>
                                <LocalDateInput
                                    name="date"
                                    label="Tanggal perjalanan"
                                />
                                <label>
                                    Nominal pengajuan (Rp)
                                    <input
                                        name="amount"
                                        type="number"
                                        min="1"
                                        max="100000000"
                                        inputMode="numeric"
                                        required
                                    />
                                </label>
                                {category.startsWith("fuel") && (
                                    <>
                                        <label>
                                            KM / odometer awal
                                            <input
                                                name="odometer"
                                                type="number"
                                                min="0"
                                                required
                                            />
                                        </label>
                                        <p class="footnote">
                                            Tanggal bisnis:{" "}
                                            {identity.businessDate}. Pengajuan
                                            BBM H-1 memerlukan foto odometer;
                                            realisasi memerlukan struk dan foto
                                            odometer setelah isi.
                                        </p>
                                    </>
                                )}
                                <label>
                                    Tujuan / alasan
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                                <EvidenceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                />
                            </>
                        )}
                        {dialog.type === "attendance" && (
                            <>
                                <label>
                                    Aktivitas
                                    <select
                                        name="event"
                                        value={dialog.event ?? "check_in"}
                                        disabled
                                    >
                                        <option value="check_in">
                                            Absensi Masuk (Checkin)
                                        </option>
                                        <option value="check_out">
                                            Absensi Keluar (Checkout)
                                        </option>
                                    </select>
                                </label>
                                <AttendanceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                    employeeName={identity.name}
                                    companyName={
                                        identity.companyName ??
                                        `Perusahaan #${identity.companyId}`
                                    }
                                    mapSite={
                                        snapshot.office
                                            ? {
                                                  ...snapshot.office,
                                                  simulated:
                                                      snapshot.office
                                                          .coordinate_status !==
                                                      "verified",
                                              }
                                            : undefined
                                    }
                                />
                            </>
                        )}
                        {dialog.type === "proof" && (
                            <>
                                <p class="muted">{dialog.delivery}</p>
                                <label>
                                    Hasil serah terima
                                    <select name="result">
                                        <option value="accepted">
                                            Diterima lengkap
                                        </option>
                                        <option value="partial">
                                            Diterima sebagian / retur
                                        </option>
                                    </select>
                                </label>
                                <p class="notice">
                                    Bukti lokal · status DO menunggu validasi
                                    server.
                                </p>
                                <EvidenceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                />
                            </>
                        )}
                        {dialog.type === "leave" && (
                            <>
                                <LocalDateInput
                                    name="from"
                                    label="Tanggal mulai"
                                />
                                <LocalDateInput
                                    name="to"
                                    label="Tanggal selesai"
                                />
                                <label>
                                    Alasan
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                                <p class="footnote">
                                    Pengajuan menunggu validasi saldo cuti dan
                                    persetujuan atasan.
                                </p>
                            </>
                        )}
                        {dialog.type === "profile" && (
                            <div
                                style={{
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "16px",
                                }}
                            >
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "14px",
                                        padding: "14px",
                                        background: "#f8fafc",
                                        borderRadius: "14px",
                                        border: "1px solid #e2e8f0",
                                    }}
                                >
                                    <span class="avatar large">
                                        {identity.name[0]}
                                    </span>
                                    <div>
                                        <h3
                                            style={{
                                                fontSize: "1.1rem",
                                                fontWeight: "700",
                                                margin: 0,
                                            }}
                                        >
                                            {identity.name}
                                        </h3>
                                        <p
                                            class="muted"
                                            style={{ margin: "2px 0 0" }}
                                        >
                                            {identity.title}
                                        </p>
                                        <small
                                            style={{
                                                color: "#004ecc",
                                                fontWeight: "600",
                                                display: "block",
                                                marginTop: "2px",
                                            }}
                                        >
                                            PT Manado Distribusi Utama
                                        </small>
                                    </div>
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: "8px",
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Perusahaan</span>
                                        <strong>
                                            PT Manado Distribusi Utama
                                        </strong>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Gudang & Hub</span>
                                        <strong>
                                            {snapshot.warehouseName ??
                                                (snapshot.scope?.warehouse_id
                                                    ? `Gudang ${snapshot.scope.warehouse_id}`
                                                    : "Belum tersedia")}
                                        </strong>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Rute & Sesi</span>
                                        <strong>{workStatus}</strong>
                                    </div>
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: "10px",
                                        marginTop: "10px",
                                    }}
                                >
                                    <a
                                        href="/web/login?redirect=/field/"
                                        class="button primary"
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            gap: "8px",
                                            padding: "12px",
                                            background: "#001a57",
                                            color: "#ffffff",
                                            borderRadius: "10px",
                                            textDecoration: "none",
                                            fontWeight: "600",
                                            fontSize: "0.95rem",
                                        }}
                                    >
                                        <Icon name="user" size={18} /> Masuk
                                        Akun Odoo / Ganti Akun
                                    </a>
                                    <a
                                        href="/web/session/logout?redirect=/field/"
                                        class="button secondary"
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            gap: "8px",
                                            padding: "12px",
                                            background: "#fff0f0",
                                            color: "#dc2626",
                                            border: "1px solid #fecaca",
                                            borderRadius: "10px",
                                            textDecoration: "none",
                                            fontWeight: "600",
                                            fontSize: "0.95rem",
                                        }}
                                    >
                                        <Icon name="close" size={18} /> Keluar
                                        dari Sesi (Logout)
                                    </a>
                                </div>
                            </div>
                        )}
                        {error && (
                            <div class="error-box" role="alert">
                                <Icon name="warning" size={20} />
                                {error}
                            </div>
                        )}
                    </div>
                    {dialog.type !== "profile" ? (
                        <footer
                            class={`sheet-footer${dialog.type === "order" ? " order-footer" : ""}`}
                        >
                            {dialog.type === "order" ? (
                                <>
                                    <OrderSummary
                                        snapshot={snapshot}
                                        qty={qty}
                                        units={units}
                                        discount={discount}
                                    />
                                    {!evidence && (
                                        <p class="summary-hint">
                                            Foto display outlet wajib sebelum
                                            order dikirim.
                                        </p>
                                    )}
                                    {orderPreview ? (
                                        <>
                                            <button
                                                type="button"
                                                class="secondary"
                                                onClick={() =>
                                                    setOrderPreview(false)
                                                }
                                            >
                                                Ubah order
                                            </button>
                                            <button
                                                type="submit"
                                                class="order-submit"
                                                disabled={
                                                    busy ||
                                                    !restored ||
                                                    !orderLines.length ||
                                                    !evidence
                                                }
                                            >
                                                {busy
                                                    ? "Mengirim…"
                                                    : "Kirim order"}
                                            </button>
                                        </>
                                    ) : (
                                        <button
                                            type="button"
                                            class="order-submit"
                                            disabled={
                                                busy ||
                                                !restored ||
                                                !orderLines.length ||
                                                !evidence
                                            }
                                            onClick={() =>
                                                setOrderPreview(true)
                                            }
                                        >
                                            Preview order
                                        </button>
                                    )}
                                </>
                            ) : (
                                <>
                                    <button
                                        type="button"
                                        class="secondary"
                                        onClick={close}
                                        disabled={busy}
                                    >
                                        Kembali
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={
                                            busy ||
                                            !restored ||
                                            (dialog.type === "attendance" &&
                                                !evidence)
                                        }
                                    >
                                        {busy
                                            ? "Menyimpan…"
                                            : dialog.type === "attendance"
                                              ? dialog.event === "check_out"
                                                  ? "Check out"
                                                  : "Check in"
                                              : "Simpan ke antrean"}
                                    </button>
                                </>
                            )}
                        </footer>
                    ) : (
                        <footer
                            class="sheet-footer"
                            style={{ justifyContent: "center" }}
                        >
                            <button
                                type="button"
                                class="secondary full"
                                onClick={close}
                                style={{ margin: 0 }}
                            >
                                Tutup
                            </button>
                        </footer>
                    )}
                </form>
            </section>
        </div>
    );
}
