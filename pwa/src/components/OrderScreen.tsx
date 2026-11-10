import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
    validateOrder,
    type FieldProvider,
    type Snapshot,
} from "../domain/contracts";
import { lineChecks } from "../domain/order-pricing";
import { quoteV2 } from "../domain/order-discount";
import type {
    DiscountProgram,
    FooterDiscount,
    LineDiscount,
} from "../domain/order-discount";
import { money } from "../domain/format";
import {
    cartTotals,
    cartFromLegacy,
    pcsOf,
    setTier,
    stockText,
    tierText,
    type Cart,
    type LineDiscounts,
} from "../domain/order-cart";
import type { OrderUom } from "../domain/order-pricing";
import { unitOptions, productUnitLabels } from "../domain/product-units";
import type { FieldStore, QueueItem } from "../storage/store";
import {
    ActionCaption,
    BottomSheet,
    Button,
    Callout,
    Card,
    IconButton,
    Screen,
    ScreenHeader,
    Chip,
    Stepper,
    Textarea,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import { Icon } from "./Icon";
import { DisplayStockScreen, displayKey } from "./DisplayStockScreen";
import { OrderResult } from "./OrderResult";
import { loadSkuPhoto } from "../domain/sku-photo";
import { DiscountSheet } from "./DiscountSheets";

type Sheet = null | "summary" | "footer" | { sku: string } | { disc: string };

export function ProductCard({
    product,
    catalogVersion,
    tiers,
    stock,
    discounts,
    onTier,
    onInfo,
    onDiscount,
}: {
    product: Snapshot["products"][number];
    catalogVersion?: 2;
    tiers: Partial<Record<OrderUom, number>>;
    stock: number;
    discounts: LineDiscount[];
    onTier: (uom: OrderUom, value: number) => void;
    onInfo: () => void;
    onDiscount: () => void;
}) {
    const options = unitOptions(product, catalogVersion);
    const pcs = pcsOf(product, tiers, catalogVersion);
    const gross = Math.round(
        (product.price * pcs) /
            (options.find((o) => o.uom === "carton")?.per ?? 1),
    );
    let subtotal = gross;
    for (const d of discounts)
        subtotal -= Math.round((subtotal * d.percent) / 100);
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
                                : stockText(product, stock, catalogVersion)}
                        </span>
                    </span>
                </div>
                <div class="pos-card__actions">
                    <IconButton
                        box
                        icon="image"
                        label={`Detail SKU ${product.name}`}
                        onClick={onInfo}
                    />
                    <IconButton
                        box
                        icon="tag"
                        label={`Diskon baris ${product.name}`}
                        onClick={onDiscount}
                        badge={discounts.length || undefined}
                        disabled={pcs <= 0}
                    />
                </div>
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
    const [photo, setPhoto] = useState<string | null>(null);
    useEffect(() => {
        let active = true;
        void loadSkuPhoto(product.image_url, product.image_version).then(
            (url) => active && setPhoto(url),
        );
        return () => {
            active = false;
        };
    }, [product.image_url, product.image_version]);
    const chain = options
        .slice(0, -1)
        .map((o) => `1 ${o.label.toLowerCase()} = ${o.per} pcs`)
        .join(" · ");
    return (
        <BottomSheet title={product.name} onClose={onClose}>
            {photo ? (
                <img
                    class="pos-photo pos-photo--img"
                    src={photo}
                    alt={`Foto ${product.name}`}
                />
            ) : (
                <div
                    class="pos-photo"
                    role="img"
                    aria-label="Foto SKU belum tersedia"
                >
                    <Icon name="image" size={40} />
                    <span>Foto SKU belum tersedia</span>
                </div>
            )}
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
                    <p>{stockText(product, stock, catalogVersion)}</p>
                </div>
            </div>
            <Button variant="sec" onClick={onClose}>
                Tutup
            </Button>
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
    const [lineDisc, setLineDisc] = useState<LineDiscounts>({});
    const [footerDisc, setFooterDisc] = useState<FooterDiscount[]>([]);
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
                        lineDiscounts?: LineDiscounts;
                        footerDiscounts?: FooterDiscount[];
                        poNumber?: string;
                        note?: string;
                    };
                    setCart(v.cart ?? cartFromLegacy(v.quantities, v.units));
                    if (v.principal) setPrincipal(v.principal);
                    setLineDisc(v.lineDiscounts ?? {});
                    setFooterDisc(v.footerDiscounts ?? []);
                    // Mockup: satu kolom "Catatan / No. PO"; draf lama memiliki dua.
                    setNote([v.poNumber, v.note].filter(Boolean).join(" · "));
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
                lineDiscounts: lineDisc,
                footerDiscounts: footerDisc,
                note,
            })
            .catch(() =>
                setError("Draft gagal disimpan. Periksa penyimpanan."),
            );
    }, [cart, principal, lineDisc, footerDisc, note, restored]);

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
    const totals = cartTotals(cart, lineDisc, footerDisc, snapshot);
    const programs = snapshot.discount_programs ?? [];
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
    const creditLeft =
        creditLimit === null
            ? null
            : creditLimit - (outlet?.commercial?.ar_outstanding ?? 0);
    const overCredit = creditLeft !== null && totals.total > creditLeft;
    const approvalReasons = [
        ...(totals.quote.tactical ? ["tactical discount"] : []),
        ...(overCredit ? ["limit kredit"] : []),
    ];
    /** Pemakaian budget program oleh seluruh keranjang kecuali bagian `skip`. */
    function usageExcept(skip: { line?: string; footer?: boolean }) {
        const lines = totals.lines.filter((l) => l.product_id !== skip.line);
        const q = quoteV2(lines, skip.footer ? [] : footerDisc, snapshot);
        return q.usage;
    }

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
        const invalid = validateOrder(lineChecks(totals.lines), snapshot);
        if (invalid) {
            setError(invalid);
            return;
        }
        setBusy(true);
        try {
            const item = await submit(
                "sales.order.submit",
                {
                    outlet_id: outletId,
                    snapshot_version: snapshot.version,
                    lines: totals.lines,
                    pricing_version: 2,
                    ...(footerDisc.length
                        ? { footer_discounts: footerDisc }
                        : {}),
                    note: note.trim(),
                    observed_total: String(totals.total),
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
        sheet && typeof sheet === "object" && "sku" in sheet
            ? snapshot.products.find((p) => p.id === sheet.sku)
            : undefined;
    const lineProduct =
        sheet && typeof sheet === "object" && "disc" in sheet
            ? snapshot.products.find((p) => p.id === sheet.disc)
            : undefined;
    const linePreviewGross = lineProduct
        ? Math.round(
              (lineProduct.price *
                  pcsOf(
                      lineProduct,
                      cart[lineProduct.id] ?? {},
                      catalogVersion,
                  )) /
                  (unitOptions(lineProduct, catalogVersion)[0]?.per ?? 1),
          )
        : 0;
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
                        onClick={() => setSheet("footer")}
                        disabled={!totals.skuCount}
                    >
                        {totals.quote.footerDiscount > 0
                            ? `Diskon footer · −${money(totals.quote.footerDiscount)}`
                            : "Diskon footer"}
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
                    Limit kredit terlampaui · order menunggu approval
                </Callout>
            ) : null}
            {totals.errors.length ? (
                <Callout tone="bad" alert>
                    {totals.errors[0]}
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
                    discounts={lineDisc[product.id] ?? []}
                    onDiscount={() => setSheet({ disc: product.id })}
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
                        {totals.quote.lines.map((ql) => {
                            const product = snapshot.products.find(
                                (p) => p.id === ql.product_id,
                            );
                            if (!product) return null;
                            const tiers = cart[ql.product_id] ?? {};
                            const discounts = lineDisc[ql.product_id] ?? [];
                            return (
                                <div class="pos-line" key={ql.product_id}>
                                    <div>
                                        <strong>{product.name}</strong>
                                        <span class="ui-row__sub">
                                            {product.sku_code ?? product.id} ·{" "}
                                            {tierText(product, tiers)} ({ql.pcs}{" "}
                                            pcs)
                                        </span>
                                    </div>
                                    <div class="pos-line__amt">
                                        {discounts.length ? (
                                            <>
                                                <Chip tone="warn">
                                                    {discounts
                                                        .map(
                                                            (d) =>
                                                                `${d.percent}%`,
                                                        )
                                                        .join(" + ")}
                                                </Chip>
                                                <span class="pos-line__old">
                                                    {money(ql.gross)}
                                                </span>
                                            </>
                                        ) : null}
                                        <strong>{money(ql.net)}</strong>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    <div class="pos-totals">
                        <div>
                            <span>Subtotal</span>
                            <strong>{money(totals.gross)}</strong>
                        </div>
                        {totals.quote.lineDiscount > 0 ? (
                            <div>
                                <span>Diskon baris</span>
                                <strong class="pos-neg">
                                    −{money(totals.quote.lineDiscount)}
                                </strong>
                            </div>
                        ) : null}
                        {totals.quote.footerDiscount > 0 ? (
                            <div>
                                <span>Diskon footer</span>
                                <strong class="pos-neg">
                                    −{money(totals.quote.footerDiscount)}
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
                    <Textarea
                        label="Catatan / No. PO (opsional)"
                        value={note}
                        maxLength={500}
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
            {lineProduct ? (
                <DiscountSheet<LineDiscount>
                    mode="line"
                    title={`Diskon baris · ${lineProduct.name}`}
                    base={
                        totals.quote.lines.find(
                            (l) => l.product_id === lineProduct.id,
                        )?.gross ?? linePreviewGross
                    }
                    programs={programs.filter(
                        (p: DiscountProgram) =>
                            p.scope === "line" &&
                            (!p.principal ||
                                p.principal === lineProduct.principal) &&
                            (!p.product_ids?.length ||
                                p.product_ids.includes(lineProduct.id)),
                    )}
                    usedElsewhere={usageExcept({ line: lineProduct.id })}
                    initial={lineDisc[lineProduct.id] ?? []}
                    onClose={() => setSheet(null)}
                    onApply={(next) => {
                        setLineDisc((cur) => {
                            const copy = { ...cur };
                            if (next.length) copy[lineProduct.id] = next;
                            else delete copy[lineProduct.id];
                            return copy;
                        });
                        setSheet(null);
                    }}
                />
            ) : null}
            {sheet === "footer" ? (
                <DiscountSheet<FooterDiscount>
                    mode="footer"
                    title="Diskon footer order"
                    base={totals.quote.afterLine}
                    programs={programs.filter(
                        (p: DiscountProgram) =>
                            p.scope === "footer" &&
                            (!p.principal || p.principal === activePrincipal),
                    )}
                    usedElsewhere={usageExcept({ footer: true })}
                    initial={footerDisc}
                    onClose={() => setSheet(null)}
                    onApply={(next) => {
                        setFooterDisc(next);
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
