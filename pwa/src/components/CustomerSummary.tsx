import type { Snapshot } from "../domain/contracts";

import { OutletAvatar } from "./OutletAvatar";
export function CustomerSummary({
    outlet,
}: {
    outlet: Snapshot["outlets"][number];
}) {
    const stats = outlet.commercial;
    const currency = new Intl.NumberFormat("id-ID", {
        style: "currency",
        currency: stats?.currency ?? "IDR",
        maximumFractionDigits: 0,
    });
    return (
        <header class="customer-summary">
            <div class="customer-identity">
                <OutletAvatar url={outlet.image_url} name={outlet.name} />
                <div>
                    <h2>{outlet.name}</h2>
                    <p>{outlet.address}</p>
                </div>
            </div>
            <dl class="customer-metrics">
                <div title="Nilai SO terkonfirmasi terbesar yang dapat dibaca akun, sebelum pajak">
                    <dt>Omset terbesar</dt>
                    <dd>
                        {stats?.max_order != null
                            ? currency.format(stats.max_order)
                            : "—"}
                    </dd>
                </div>
                <div title="Belum tersedia bila kunjungan resmi belum terintegrasi">
                    <dt>Kunj. sebelumnya</dt>
                    <dd>
                        {stats?.previous_visit_total != null
                            ? currency.format(stats.previous_visit_total)
                            : "—"}
                    </dd>
                </div>
                <div>
                    <dt>Top order SKU</dt>
                    <dd>{stats?.top_sku ?? "—"}</dd>
                </div>
            </dl>
            <p class="customer-terms">
                <span>TOP: {stats?.payment_terms ?? "—"}</span>
                {stats?.credit_limit != null && (
                    <span>Limit: {currency.format(stats.credit_limit)}</span>
                )}
                <span>PIC: {stats?.contact ?? "—"}</span>
            </p>
        </header>
    );
}
