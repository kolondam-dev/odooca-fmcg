import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
    validateOrder,
    type FieldProvider,
    type Snapshot,
} from "../domain/contracts";
import { money } from "../domain/format";
import {
    cartTotals,
    cartFromLegacy,
    pcsOf,
    setTier,
    tierText,
    type Cart,
} from "../domain/order-cart";
import { orderQuote, type OrderUom } from "../domain/order-pricing";
import { unitOptions, productUnitLabels } from "../domain/product-units";
import type { FieldStore, QueueItem } from "../storage/store";
import {
    ActionCaption,
    BottomSheet,
    Button,
    Callout,
    Card,
    Field,
    IconButton,
    Screen,
    ScreenHeader,
    Select,
    Stepper,
    Textarea,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import { Icon } from "./Icon";
import { DisplayStockScreen, displayKey } from "./DisplayStockScreen";
import { OrderResult } from "./OrderResult";

/** Alasan baku diskon; kontrak menerima teks bebas 3–500 karakter. */
export const DISCOUNT_REASONS = [
    "Pembeli minta potongan ongkos",
    "Kompetitor lebih murah",
    "Program promo belum tersedia di sistem",
    "Lainnya",
];

type Sheet = null | "summary" | "discount" | { sku: string };

const stockText = (value: number, carton: string) =>
    `${Number.isInteger(value) ? value : value.toFixed(1)} ${carton.toLowerCase().slice(0, 3) === "kar" ? "krt" : carton.toLowerCase()}`;

function ProductCard({
    product,
    catalogVersion,
    tiers,
    stock,
    onTier,
    onInfo,
}: {
    product: Snapshot["products"][number];
    catalogVersion?: 2;
    tiers: Partial<Record<OrderUom, number>>;
    stock: number;
    onTier: (uom: OrderUom, value: number) => void;
    onInfo: () => void;
}) {
    const options = unitOptions(product, catalogVersion);
    const pcs = pcsOf(product, tiers, catalogVersion);
    const subtotal = Math.round(
        (product.price * pcs) /
            (options.find((o) => o.uom === "carton")?.per ?? 1),
    );
    const labels = productUnitLabels(product);
    const cartons = pcs / (options[0]?.per ?? 1);
    return (
        <Card class="pos-card">
            <div class="pos-card__head">
                <div class="pos-card__id">
                    <h3 class="pos-card__name">{product.name}</h3>
                    <span class="ui-row__sub pos-card__meta">
                        {product.sku_code ?? product.id} ·{" "}
                        <Icon name="box" size={14} />{" "}
                        <span
                            class={stock <= 0 ? "pos-card__out" : undefined}
                            aria-label={`Stok ${stock} ${labels.carton}`}
                        >
                            {stock <= 0
                                ? "Habis"
                                : stockText(stock, labels.carton)}
                        </span>
                    </span>
                </div>
                <IconButton
                    box
                    icon="image"
                    label={`Detail SKU ${product.name}`}
                    onClick={onInfo}
                />
            </div>
            {options.map((option) => (
                <div class="pos-tier" key={option.uom}>
                    <div class="pos-tier__id">
                        <span class="pos-tier__name">{option.label}</span>
                        <span class="ui-row__sub">
                            {money(
                                Math.round(
                                    (product.price * option.per) /
                                        (options[0]?.per ?? 1),
                                ),
                            )}
                        </span>
                    </div>
                    <Stepper
                        value={tiers[option.uom] ?? 0}
                        max={999}
                        unit={`${product.name} ${option.label}`}
                        label={`Kuantitas ${product.name} ${option.label}`}
                        onChange={(value) => onTier(option.uom, value)}
                    />
                </div>
            ))}
            {pcs > 0 ? (
                <div class="pos-card__sum">
                    <span class="ui-row__sub">
                        {pcs} pcs · {Number(cartons.toFixed(2))} {labels.carton}
                    </span>
                    <strong>{money(subtotal)}</strong>
                </div>
            ) : null}
            {pcs > 0 && cartons > stock ? (
                <Callout tone="warn" alert>
                    Jumlah ({Number(cartons.toFixed(2))} {labels.carton})
                    melebihi stok sistem ({stock}).
                </Callout>
            ) : null}
        </Card>
    );
}

function SkuSheet({
    product,
    catalogVersion,
    stock,
    onClose,
}: {
    product: Snapshot["products"][number];
    catalogVersion?: 2;
    stock: number;
    onClose: () => void;
}) {
    const options = unitOptions(product, catalogVersion);
    const carton = options[0]?.per ?? 1;
    const labels = productUnitLabels(product);
    const chain = options
        .slice(0, -1)
        .map((o) => `1 ${o.label.toLowerCase()} = ${o.per} pcs`)
        .join(" · ");
    return (
        <BottomSheet title={product.name} onClose={onClose}>
            <div
                class="pos-photo"
                role="img"
                aria-label="Foto SKU belum tersedia"
            >
                <Icon name="image" size={40} />
                <span>Foto SKU belum tersedia</span>
            </div>
            <div class="pos-facts">
                <div>
                    <h3>SKU</h3>
                    <p>
                        {product.sku_code ?? product.id} · {product.brand}
                    </p>
                </div>
                <div>
                    <h3>Isi kemasan</h3>
                    <p>{chain || "Satuan tunggal"}</p>
                </div>
                <div>
                    <h3>Harga</h3>
                    <p>
                        {options
                            .map(
                                (o) =>
                                    `${money(Math.round((product.price * o.per) / carton))} / ${o.label.toLowerCase()}`,
                            )
                            .join(" · ")}
                    </p>
                </div>
                <div>
                    <h3>Stok sistem</h3>
                    <p>
                        {stock} {labels.carton.toLowerCase()}
                    </p>
                </div>
            </div>
            <Button variant="sec" onClick={onClose}>
                Tutup
            </Button>
        </BottomSheet>
    );
}

function DiscountSheet({
    percent,
    reason,
    base,
    onApply,
    onClose,
}: {
    percent: number;
    reason: string;
    base: number;
    onApply: (percent: number, reason: string) => void;
    onClose: () => void;
}) {
    const preset = DISCOUNT_REASONS.includes(reason) ? reason : "";
    const [value, setValue] = useState(percent ? String(percent) : "");
    const [choice, setChoice] = useState(
        preset || (reason ? "Lainnya" : DISCOUNT_REASONS[0]),
    );
    const [other, setOther] = useState(preset ? "" : reason);
    const n = Number(value);
    const valid = Number.isInteger(n) && n >= 1 && n <= 100;
    const text = choice === "Lainnya" ? other.trim() : choice;
    const ok = valid && text.length >= 3;
    return (
        <BottomSheet title="Diskon order" onClose={onClose}>
            <Callout tone="neu">Subtotal sebelum diskon: {money(base)}</Callout>
            <Card>
                <Field
                    label="Diskon diminta (%)"
                    type="text"
                    inputMode="numeric"
                    value={value}
                    onInput={(v) => setValue(v.replace(/\D/g, "").slice(0, 3))}
                    hint={
                        valid
                            ? `−${money(Math.round((base * n) / 100))} · perlu approval supervisor`
                            : "Isi 1–100"
                    }
                />
                <Select
                    label="Alasan (wajib)"
                    options={DISCOUNT_REASONS.map((r) => ({
                        value: r,
                        label: r,
                    }))}
                    value={choice}
                    onChange={setChoice}
                />
                {choice === "Lainnya" ? (
                    <Textarea
                        label="Alasan permintaan diskon"
                        value={other}
                        maxLength={500}
                        onInput={setOther}
                    />
                ) : null}
            </Card>
            <Button
                icon="check"
                disabled={!ok}
                onClick={() => onApply(n, text)}
            >
                Terapkan diskon
            </Button>
            {percent > 0 ? (
                <Button variant="sec" onClick={() => onApply(0, "")}>
                    Hapus diskon
                </Button>
            ) : null}
        </BottomSheet>
    );
}

export function OrderScreen({
    snapshot,
    outletId,
    owner,
    store,
    provider,
    queue,
    submit,
    close,
    finishVisit,
}: {
    snapshot: Snapshot;
    outletId: string;
    owner: string;
    store: FieldStore;
    provider?: FieldProvider;
    queue: QueueItem[];
    submit: (
        type: "sales.order.submit",
        payload: Record<string, unknown>,
        label: string,
        keepOpen: true,
    ) => Promise<QueueItem>;
    close: () => void;
    finishVisit: () => void;
}) {
    const outlet = snapshot.outlets.find((o) => o.id === outletId);
    const catalogVersion = snapshot.catalog_version;
    const principals = useMemo(
        () => [...new Set(snapshot.products.map((p) => p.principal))],
        [snapshot.products],
    );
    const [cart, setCart] = useState<Cart>({});
    const [principal, setPrincipal] = useState(principals[0] ?? "");
    const [percent, setPercent] = useState(0);
    const [reason, setReason] = useState("");
    const [po, setPo] = useState("");
    const [note, setNote] = useState("");
    const [query, setQuery] = useState("");
    const [limit, setLimit] = useState(40);
    const [sheet, setSheet] = useState<Sheet>(null);
    const [restored, setRestored] = useState(false);
    const [display, setDisplay] = useState<boolean | undefined>();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [done, setDone] = useState<QueueItem | undefined>();
    const [lockHint, setLockHint] = useState(false);
    const [displayOpen, setDisplayOpen] = useState(false);
    const [stock, setStock] = useState<Record<string, number>>(() =>
        Object.fromEntries(snapshot.products.map((p) => [p.id, p.stock])),
    );
    const key = `order:${outletId}`;
    const opener = useRef<Element | null>(document.activeElement);
    // Satu lapis Back selama Order/Hasil kirim terbuka; lembar anak menumpuk di atasnya.
    useBackLayer(true, () => {
        if (!busy) close();
    });
    useEffect(
        () => () => {
            const el = opener.current;
            if (el instanceof HTMLElement && el.isConnected)
                setTimeout(() => el.focus(), 0);
        },
        [],
    );
    // Stok aktual: snapshot tetap kontrak harga; stok diperbarui berkala.
    useEffect(() => {
        if (!provider) return;
        let active = true;
        const pull = () =>
            void provider
                .snapshot()
                .then((fresh: Snapshot) => {
                    if (!active || !fresh?.products?.length) return;
                    setStock((prev) => ({
                        ...prev,
                        ...Object.fromEntries(
                            fresh.products.map((p) => [p.id, p.stock]),
                        ),
                    }));
                })
                .catch(() => {});
        pull();
        const timer = setInterval(pull, 20_000);
        return () => {
            active = false;
            clearInterval(timer);
        };
    }, [provider]);
    useEffect(() => {
        let active = true;
        void store
            .draft(owner, key)
            .then((value) => {
                if (!active) return;
                if (value && typeof value === "object") {
                    const v = value as {
                        cart?: Cart;
                        quantities?: Record<string, number>;
                        units?: Record<string, OrderUom>;
                        principal?: string;
                        discount?: number;
                        discountReason?: string;
                        poNumber?: string;
                        note?: string;
                    };
                    setCart(v.cart ?? cartFromLegacy(v.quantities, v.units));
                    if (v.principal) setPrincipal(v.principal);
                    setPercent(v.discount ?? 0);
                    setReason(v.discountReason ?? "");
                    setPo(v.poNumber ?? "");
                    setNote(v.note ?? "");
                }
                setRestored(true);
            })
            .catch(() => {
                setError("Draft tidak dapat dibaca.");
                setRestored(true);
            });
        return () => {
            active = false;
        };
    }, []);
    useEffect(() => {
        if (displayOpen) return;
        let active = true;
        void store
            .draft(owner, displayKey(outletId))
            .then((value) => {
                if (active)
                    setDisplay(
                        !!(
                            value &&
                            typeof value === "object" &&
                            (value as { evidence?: unknown }).evidence
                        ),
                    );
            })
            .catch(() => active && setDisplay(false));
        return () => {
            active = false;
        };
    }, [displayOpen]);
    useEffect(() => {
        if (!restored || done) return;
        void store
            .draft(owner, key, {
                cart,
                principal,
                discount: percent,
                discountReason: reason,
                poNumber: po,
                note,
            })
            .catch(() =>
                setError("Draft gagal disimpan. Periksa penyimpanan."),
            );
    }, [cart, principal, percent, reason, po, note, restored]);

    const term = query.trim().toLowerCase();
    const activePrincipal = principals.includes(principal)
        ? principal
        : (principals[0] ?? principal);
    const products = useMemo(
        () =>
            snapshot.products.filter(
                (p) =>
                    p.principal === activePrincipal &&
                    (!term ||
                        `${p.name} ${p.sku_code ?? ""} ${p.brand}`
                            .toLowerCase()
                            .includes(term)),
            ),
        [snapshot.products, activePrincipal, term],
    );
    useEffect(() => setLimit(40), [activePrincipal, term]);
    const totals = cartTotals(cart, snapshot, percent);
    const principalName =
        snapshot.products.find((p) => p.principal === activePrincipal)
            ?.principal_name ??
        activePrincipal.charAt(0).toUpperCase() + activePrincipal.slice(1);
    const cartEmpty = totals.skuCount === 0;
    const staleItems = totals.stale;
    function dropStale() {
        setCart((current) => {
            const next = { ...current };
            for (const id of staleItems) delete next[id];
            return next;
        });
    }
    const creditLimit = outlet?.commercial?.credit_limit ?? null;
    const overCredit = creditLimit !== null && totals.total > creditLimit;
    const approvalReasons = [
        ...(percent > 0 ? ["diskon"] : []),
        ...(overCredit ? ["limit kredit"] : []),
    ];

    async function send() {
        if (busy) return;
        setError("");
        if (!display) {
            setError("Foto display toko wajib sebelum order dikirim.");
            return;
        }
        if (staleItems.length) {
            setError(
                `${staleItems.length} SKU di draft sudah tidak ada di katalog. Hapus dari draft sebelum mengirim.`,
            );
            return;
        }
        if (totals.errors.length) {
            setError(totals.errors[0]!);
            return;
        }
        const invalid = validateOrder(
            totals.lines.map((l) => ({
                productId: l.product_id,
                quantity: Number(l.qty),
            })),
            snapshot,
        );
        if (invalid) {
            setError(invalid);
            return;
        }
        if (percent > 0 && reason.trim().length < 3) {
            setError("Alasan diskon wajib diisi.");
            return;
        }
        setBusy(true);
        try {
            const discount =
                percent > 0 ? { percent, reason: reason.trim() } : undefined;
            const item = await submit(
                "sales.order.submit",
                {
                    outlet_id: outletId,
                    snapshot_version: snapshot.version,
                    lines: totals.lines,
                    customer_po_number: po.trim() || undefined,
                    pricing_version: 1,
                    ...(discount ? { discount_request: discount } : {}),
                    note: note.trim(),
                    observed_total: String(
                        orderQuote(totals.lines, snapshot, discount)
                            .requestedTotal,
                    ),
                },
                `Order • ${outlet?.name}`,
                true,
            );
            await store.removeDraft(owner, key);
            setSheet(null);
            setDone(item);
        } catch (x) {
            setError(
                x instanceof Error
                    ? x.message
                    : "Penyimpanan gagal. Order tetap tersedia.",
            );
        } finally {
            setBusy(false);
        }
    }

    if (done)
        return (
            <OrderResult
                item={queue.find((q) => q.key === done.key) ?? done}
                outletName={outlet?.name ?? "Outlet"}
                total={totals.total}
                skuCount={totals.skuCount}
                approvalReasons={approvalReasons}
                close={close}
                finishVisit={finishVisit}
            />
        );

    const sku =
        sheet && typeof sheet === "object"
            ? snapshot.products.find((p) => p.id === sheet.sku)
            : undefined;
    const lockedByCart = !cartEmpty;
    return (
        <Screen
            label="Order penjualan"
            class="ui-screen--over"
            header={
                <ScreenHeader
                    title={`Order · ${outlet?.name ?? "Outlet"}`}
                    onBack={() => {
                        if (!busy) close();
                    }}
                />
            }
            footer={
                <>
                    <Button
                        variant="sec"
                        icon="tag"
                        onClick={() => setSheet("discount")}
                        disabled={!totals.skuCount}
                    >
                        {percent > 0
                            ? `Diskon order · −${money(totals.discount)}`
                            : "Diskon order"}
                    </Button>
                    <Button
                        icon="cart"
                        disabled={!restored || !totals.skuCount}
                        onClick={() => setSheet("summary")}
                    >
                        {totals.skuCount
                            ? `${totals.skuCount} SKU · ${money(totals.total)} · Lihat`
                            : "Pilih produk"}
                    </Button>
                    {error && !sheet ? (
                        <ActionCaption>{error}</ActionCaption>
                    ) : null}
                </>
            }
        >
            <div class="pos-toolbar-ds">
                <label class="pos-search">
                    <Icon name="search" size={20} />
                    <input
                        aria-label="Cari produk"
                        placeholder="Cari nama atau SKU"
                        value={query}
                        onInput={(e) => setQuery(e.currentTarget.value)}
                    />
                </label>
                {principals.length > 1 && !lockedByCart ? (
                    <label class="pos-principal">
                        <span class="ui-visually-hidden">Principal</span>
                        <select
                            aria-label="Principal"
                            value={activePrincipal}
                            onChange={(e) =>
                                setPrincipal(e.currentTarget.value)
                            }
                        >
                            {principals.map((p) => (
                                <option key={p} value={p}>
                                    {snapshot.products.find(
                                        (x) => x.principal === p,
                                    )?.principal_name ??
                                        p.charAt(0).toUpperCase() + p.slice(1)}
                                </option>
                            ))}
                        </select>
                    </label>
                ) : (
                    <button
                        type="button"
                        class="pos-principal pos-principal--locked"
                        aria-label={`Principal ${principalName} terkunci`}
                        onClick={() => setLockHint(true)}
                    >
                        <Icon name="lock" size={18} />
                        {principalName}
                    </button>
                )}
            </div>
            {lockHint && principals.length > 1 ? (
                <Callout tone="info">
                    1 order hanya untuk 1 principal. Kosongkan keranjang untuk
                    berganti.
                </Callout>
            ) : null}
            {display === false ? (
                <Callout
                    tone="warn"
                    icon="camera"
                    title="Foto display belum ada"
                >
                    <span>
                        Foto display toko wajib sebelum order dikirim.{" "}
                        <button
                            type="button"
                            class="ui-linkbtn"
                            onClick={() => setDisplayOpen(true)}
                        >
                            Buka Display & stok
                        </button>
                    </span>
                </Callout>
            ) : null}
            {staleItems.length ? (
                <Callout tone="bad" alert>
                    {staleItems.length} SKU di draft tidak ada lagi di katalog
                    terbaru dan tidak ikut terhitung.{" "}
                    <button
                        type="button"
                        class="ui-linkbtn"
                        onClick={dropStale}
                    >
                        Hapus dari draft
                    </button>
                </Callout>
            ) : null}
            {overCredit ? (
                <Callout tone="warn" icon="warning">
                    Total order melebihi limit kredit outlet ·{" "}
                    {money(creditLimit!)}. Kemungkinan perlu approval.
                </Callout>
            ) : null}
            {products.length === 0 ? (
                <p class="empty">Tidak ada produk yang cocok.</p>
            ) : null}
            {products.slice(0, limit).map((product) => (
                <ProductCard
                    key={product.id}
                    product={product}
                    catalogVersion={catalogVersion}
                    tiers={cart[product.id] ?? {}}
                    stock={stock[product.id] ?? product.stock}
                    onTier={(uom, value) =>
                        setCart((current) =>
                            setTier(current, product.id, uom, value),
                        )
                    }
                    onInfo={() => setSheet({ sku: product.id })}
                />
            ))}
            {limit < products.length ? (
                <Button
                    variant="sec"
                    onClick={() => setLimit((value) => value + 40)}
                >
                    Tampilkan produk berikutnya (
                    {Math.min(limit, products.length)}/{products.length})
                </Button>
            ) : null}
            {sheet === "summary" ? (
                <BottomSheet
                    title="Ringkasan order"
                    onClose={() => setSheet(null)}
                >
                    <div class="pos-lines">
                        {Object.entries(cart).map(([id, tiers]) => {
                            const product = snapshot.products.find(
                                (p) => p.id === id,
                            );
                            if (!product) return null;
                            const pcs = pcsOf(product, tiers, catalogVersion);
                            if (pcs <= 0) return null;
                            const per =
                                unitOptions(product, catalogVersion)[0]?.per ??
                                1;
                            return (
                                <div class="pos-line" key={id}>
                                    <div>
                                        <strong>{product.name}</strong>
                                        <span class="ui-row__sub">
                                            {product.sku_code ?? product.id} ·{" "}
                                            {tierText(product, tiers)} ({pcs}{" "}
                                            pcs)
                                        </span>
                                    </div>
                                    <strong>
                                        {money(
                                            Math.round(
                                                (product.price * pcs) / per,
                                            ),
                                        )}
                                    </strong>
                                    <button
                                        type="button"
                                        class="ui-linkbtn"
                                        aria-label={`Hapus ${product.name}`}
                                        onClick={() =>
                                            setCart((current) => {
                                                const next = { ...current };
                                                delete next[id];
                                                return next;
                                            })
                                        }
                                    >
                                        Hapus
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                    <div class="pos-totals">
                        <div>
                            <span>Subtotal</span>
                            <strong>{money(totals.gross)}</strong>
                        </div>
                        {percent > 0 ? (
                            <div>
                                <span>Diskon {percent}%</span>
                                <strong class="pos-neg">
                                    −{money(totals.discount)}
                                </strong>
                            </div>
                        ) : null}
                        <div class="pos-totals__grand">
                            <span>Total</span>
                            <strong>{money(totals.total)}</strong>
                        </div>
                    </div>
                    {approvalReasons.length ? (
                        <Callout tone="warn">
                            Menunggu approval: {approvalReasons.join(", ")}
                        </Callout>
                    ) : (
                        <Callout tone="neu">
                            Harga sesuai snapshot harian.
                        </Callout>
                    )}
                    <Field
                        label="Nomor PO outlet (opsional)"
                        value={po}
                        maxLength={64}
                        placeholder="Contoh: PO/2026/10/099"
                        onInput={setPo}
                    />
                    <Textarea
                        label="Catatan order"
                        value={note}
                        maxLength={500}
                        placeholder="Permintaan outlet (opsional)"
                        onInput={setNote}
                    />
                    {error ? (
                        <Callout tone="bad" alert>
                            {error}
                        </Callout>
                    ) : null}
                    <Button
                        disabled={busy || !restored || !display}
                        onClick={() => void send()}
                    >
                        {busy ? "Mengirim…" : "Kirim order"}
                    </Button>
                    {!display ? (
                        <ActionCaption>
                            Foto display toko wajib sebelum order dikirim.
                        </ActionCaption>
                    ) : null}
                </BottomSheet>
            ) : null}
            {sheet === "discount" ? (
                <DiscountSheet
                    percent={percent}
                    reason={reason}
                    base={totals.gross}
                    onClose={() => setSheet(null)}
                    onApply={(p, r) => {
                        setPercent(p);
                        setReason(r);
                        setSheet(null);
                    }}
                />
            ) : null}
            {displayOpen ? (
                <DisplayStockScreen
                    snapshot={snapshot}
                    outletId={outletId}
                    owner={owner}
                    store={store}
                    close={() => setDisplayOpen(false)}
                />
            ) : null}
            {sku ? (
                <SkuSheet
                    product={sku}
                    catalogVersion={catalogVersion}
                    stock={stock[sku.id] ?? sku.stock}
                    onClose={() => setSheet(null)}
                />
            ) : null}
        </Screen>
    );
}
